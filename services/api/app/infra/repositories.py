"""用户、会话和消息的数据访问层。"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Conversation, ConversationMemory, Message, User


class UserRepository:
    """封装用户查询、创建和数据授权更新。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: str) -> User | None:
        """根据前端匿名标识查询用户。"""
        statement = select(User).where(User.external_id == external_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_phone_number(self, phone_number: str) -> User | None:
        """根据手机号查询用户（登录用：手机号已绑定过就认那个老用户）。"""
        statement = select(User).where(User.phone_number == phone_number)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(
        self, user_id: UUID, *, for_update: bool = False
    ) -> User | None:
        """按内部 ID 查询用户；额度变更时可锁住用户行串行处理。"""
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
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
        persona: str = "nini",
        client_session_id: str | None = None,
    ) -> Conversation:
        """创建会话但不提交事务。"""
        conversation = Conversation(
            user_id=user_id,
            persona=persona,
            client_session_id=client_session_id,
            last_activity_at=datetime.now(UTC),
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get_for_user(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> Conversation | None:
        """按会话和用户共同查询，避免读取其他用户的会话。"""
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        if not include_deleted:
            statement = statement.where(Conversation.status != "pending_delete")
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_client_session(
        self,
        user_id: UUID,
        client_session_id: str,
    ) -> Conversation | None:
        """查找已导入的浏览器会话，用于保证导入接口幂等。"""
        statement = select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.client_session_id == client_session_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def trim_for_user(
        self,
        user_id: UUID,
        *,
        keep: int = 7,
        preserve_conversation_id: UUID | None = None,
    ) -> list[UUID]:
        """永久删除超额的最旧有效会话，并返回删除的 ID。

        `pending_delete` 已释放额度，不参与计数。恢复会话时通过 preserve 参数
        避免刚恢复的旧记录立即又成为最旧记录而被删掉。
        """
        count_statement = select(func.count(Conversation.id)).where(
            Conversation.user_id == user_id,
            Conversation.status != "pending_delete",
        )
        count = int((await self._session.execute(count_statement)).scalar_one())
        excess = max(0, count - keep)
        if excess == 0:
            return []

        candidates = select(Conversation.id).where(
            Conversation.user_id == user_id,
            Conversation.status != "pending_delete",
        )
        if preserve_conversation_id is not None:
            candidates = candidates.where(Conversation.id != preserve_conversation_id)
        candidates = candidates.order_by(
            Conversation.created_at.asc(),
            Conversation.id.asc(),
        ).limit(excess)
        stale_ids = list((await self._session.execute(candidates)).scalars().all())
        if stale_ids:
            await self._session.execute(
                delete(Conversation).where(Conversation.id.in_(stale_ids))
            )
        return stale_ids

    async def list_ended_for_user(self, user_id: UUID) -> list[Conversation]:
        """列出用户已结束归档的轮次，最新的在前。进行中的当前轮不出现在这里。"""
        statement = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.status == "closed",
                Conversation.ended_at.is_not(None),
            )
            .order_by(Conversation.ended_at.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_deleted_for_user(self, user_id: UUID) -> list[Conversation]:
        """列出仍在15天恢复期内的会话。"""
        statement = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.status == "pending_delete",
            )
            .order_by(Conversation.deleted_at.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def close(
        self,
        conversation: Conversation,
        *,
        reason: Literal["user_end", "browser_close", "idle_timeout"],
        ended_at: datetime | None = None,
    ) -> Conversation:
        """结束一轮会话；重复关闭保持幂等。"""
        if conversation.status == "active":
            conversation.status = "closed"
            conversation.close_reason = reason
            conversation.ended_at = ended_at or datetime.now(UTC)
            await self._session.flush()
        return conversation

    async def touch(self, conversation: Conversation) -> None:
        """收到新消息时刷新最后活动时间。"""
        conversation.last_activity_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_deleted(
        self,
        conversation: Conversation,
        *,
        purge_after: datetime,
    ) -> Conversation:
        """把会话放入回收站，立即释放额度。"""
        now = datetime.now(UTC)
        conversation.status = "pending_delete"
        conversation.deleted_at = now
        conversation.purge_after = purge_after
        conversation.include_in_memory = False
        await self._session.flush()
        return conversation

    async def restore(self, conversation: Conversation) -> Conversation:
        """从回收站恢复；原先结束过的记录恢复为 closed，否则为 active。"""
        conversation.status = "closed" if conversation.ended_at else "active"
        conversation.deleted_at = None
        conversation.purge_after = None
        await self._session.flush()
        return conversation

    async def close_idle_before(self, cutoff: datetime) -> list[UUID]:
        """关闭超过截止时间仍无活动的会话。"""
        statement = select(Conversation).where(
            Conversation.status == "active",
            Conversation.last_activity_at < cutoff,
        )
        conversations = list((await self._session.execute(statement)).scalars().all())
        now = datetime.now(UTC)
        for conversation in conversations:
            conversation.status = "closed"
            conversation.close_reason = "idle_timeout"
            conversation.ended_at = now
        await self._session.flush()
        return [conversation.id for conversation in conversations]

    async def purge_due(self, now: datetime) -> list[UUID]:
        """永久删除已超过15天保留期的回收站会话。"""
        statement = select(Conversation.id).where(
            Conversation.status == "pending_delete",
            Conversation.purge_after.is_not(None),
            Conversation.purge_after <= now,
        )
        conversation_ids = list(
            (await self._session.execute(statement)).scalars().all()
        )
        if conversation_ids:
            await self._session.execute(
                delete(Conversation).where(Conversation.id.in_(conversation_ids))
            )
        return conversation_ids


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

    async def list_all(self, conversation_id: UUID) -> list[Message]:
        """按时间顺序返回某一轮的完整消息（不截断），用于历史轮次回看。"""
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())


class ConversationMemoryRepository:
    """会话摘要记忆的数据访问层。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_conversation(
        self,
        conversation_id: UUID,
    ) -> ConversationMemory | None:
        statement = select(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_statuses(
        self,
        conversation_ids: list[UUID],
    ) -> dict[UUID, str]:
        """批量返回会话对应的记忆状态，避免历史列表逐条查询。"""
        if not conversation_ids:
            return {}
        statement = select(
            ConversationMemory.conversation_id,
            ConversationMemory.status,
        ).where(ConversationMemory.conversation_id.in_(conversation_ids))
        result = await self._session.execute(statement)
        return {
            conversation_id: status for conversation_id, status in result.tuples().all()
        }

    async def get_or_create(
        self,
        conversation_id: UUID,
    ) -> ConversationMemory:
        memory = await self.get_for_conversation(conversation_id)
        if memory is not None:
            return memory
        memory = ConversationMemory(conversation_id=conversation_id)
        self._session.add(memory)
        await self._session.flush()
        return memory

    async def list_ready_summaries_for_user(self, user_id: UUID) -> list[str]:
        """按会话开始时间返回用户主动启用且可用的摘要。"""
        statement = (
            select(ConversationMemory.summary)
            .join(
                Conversation,
                Conversation.id == ConversationMemory.conversation_id,
            )
            .where(
                Conversation.user_id == user_id,
                Conversation.status != "pending_delete",
                Conversation.include_in_memory.is_(True),
                ConversationMemory.status == "ready",
            )
            .order_by(Conversation.created_at.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
