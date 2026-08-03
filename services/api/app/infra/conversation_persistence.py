"""基于 PostgreSQL 的会话持久化实现。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.safety import SafetyReason
from app.infra.repositories import (
    ConversationRepository,
    MessageRepository,
    UserRepository,
)


class PostgresConversationPersistence:
    """使用同一事务保存用户、会话和一轮消息。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._conversations = ConversationRepository(session)
        self._messages = MessageRepository(session)

    async def save_exchange(
        self,
        *,
        external_user_id: str,
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
            user = await self._users.get_or_create(external_user_id)
            conversation = None
            if conversation_id is not None:
                conversation = await self._conversations.get_for_user(
                    conversation_id,
                    user.id,
                )

            if conversation is None:
                conversation = await self._conversations.create(
                    user_id=user.id,
                    persona=persona,
                )
            else:
                conversation.persona = persona

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
            await self._conversations.trim_for_user(user.id, keep=7)
            await self._session.commit()
            return conversation.id
        except Exception:
            await self._session.rollback()
            raise
