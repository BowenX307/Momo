"""基于 PostgreSQL 的会话持久化实现。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.safety import SafetyReason
from app.infra.repositories import (
    ConversationRepository,
    MessageRepository,
    UserRepository,
)


class PostgresConversationPersistence:
    """使用同一事务保存用户、会话和一轮消息。"""

    def __init__(self, session: AsyncSession, *, user_id: UUID) -> None:
        self._session = session
        self._user_id = user_id
        self._users = UserRepository(session)
        self._conversations = ConversationRepository(session)
        self._messages = MessageRepository(session)

    async def save_exchange(
        self,
        *,
        conversation_id: UUID | None,
        persona: str,
        user_text: str,
        reply: str,
        safety_flag: SafetyReason,
        emotion: str,
        request_id: str,
        is_mock: bool,
        degraded: bool,
    ) -> UUID:
        """保存整轮对话；任一步失败都会回滚本次事务。"""
        try:
            conversation = None
            if conversation_id is not None:
                conversation = await self._conversations.get_for_user(
                    conversation_id,
                    self._user_id,
                )

            if conversation is None or conversation.status != "active":
                created = True
                user = await self._users.get_by_id(self._user_id, for_update=True)
                if user is None or not user.data_consent:
                    raise PermissionError("authenticated user with consent required")
                conversation = await self._conversations.create(
                    user_id=self._user_id,
                    persona=persona,
                )
            else:
                created = False
                conversation.persona = persona
                await self._conversations.touch(conversation)

            await self._messages.create(
                conversation_id=conversation.id,
                role="user",
                content=user_text,
                safety_flag=safety_flag,
                emotion=emotion or None,
                request_id=request_id,
            )
            await self._messages.create(
                conversation_id=conversation.id,
                role="assistant",
                content=reply,
                safety_flag=safety_flag,
                request_id=request_id,
                is_mock=is_mock,
                degraded=degraded,
            )
            if created:
                await self._conversations.trim_for_user(
                    self._user_id,
                    keep=settings.free_conversation_limit,
                    preserve_conversation_id=conversation.id,
                )
            await self._session.commit()
            return conversation.id
        except Exception:
            await self._session.rollback()
            raise
