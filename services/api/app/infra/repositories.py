"""用户、会话和消息的数据访问层。"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Conversation, Message, User


class UserRepository:
    """封装用户查询、创建和数据授权更新。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: str) -> User | None:
        """根据前端匿名标识查询用户。"""
        statement = select(User).where(User.external_id == external_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_or_create(self, external_id: str) -> User:
        """返回已有用户；不存在时创建但不提交事务。"""
        user = await self.get_by_external_id(external_id)
        if user is not None:
            return user

        user = User(external_id=external_id)
        self._session.add(user)
        await self._session.flush()
        return user

    async def set_data_consent(
        self,
        user: User,
        *,
        granted: bool,
        version: str | None,
    ) -> User:
        """更新用户的数据授权状态，但不提交事务。"""
        user.data_consent = granted
        user.consent_version = version if granted else None
        user.consented_at = datetime.now(UTC) if granted else None
        await self._session.flush()
        return user


class ConversationRepository:
    """封装聊天会话的创建和按用户查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        scene: str | None,
        persona: str = "nini",
    ) -> Conversation:
        """创建会话但不提交事务。"""
        conversation = Conversation(
            user_id=user_id,
            scene=scene,
            persona=persona,
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get_for_user(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation | None:
        """按会话和用户共同查询，避免读取其他用户的会话。"""
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def trim_for_user(self, user_id: UUID, *, keep: int = 7) -> None:
        """只保留用户最近的若干次浏览器会话。"""
        stale_ids = (
            select(Conversation.id)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .offset(keep)
        )
        await self._session.execute(
            delete(Conversation).where(Conversation.id.in_(stale_ids))
        )


class MessageRepository:
    """封装消息写入和最近消息查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        conversation_id: UUID,
        role: Literal["user", "assistant"],
        content: str,
        safety_flag: str = "ok",
        emotion: str | None = None,
        request_id: str | None = None,
        is_mock: bool = False,
        degraded: bool = False,
    ) -> Message:
        """创建一条消息但不提交事务。"""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            safety_flag=safety_flag,
            emotion=emotion,
            request_id=request_id,
            is_mock=is_mock,
            degraded=degraded,
            created_at=datetime.now(UTC),
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_recent(
        self,
        conversation_id: UUID,
        *,
        limit: int = 20,
    ) -> list[Message]:
        """按时间顺序返回会话最近的消息。"""
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages
