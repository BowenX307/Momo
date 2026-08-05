"""历史轮次读取，以及登录用户的导入、删除和恢复策略。"""

from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.conversation.schemas import (
    ImportConversationRequest,
    Persona,
    RoundMessage,
    RoundSummary,
)
from app.infra.models import Conversation, Message
from app.infra.repositories import (
    ConversationMemoryRepository,
    ConversationRepository,
    MessageRepository,
    UserRepository,
)

MemoryStatus = Literal["pending", "ready", "failed", "stale"]


def _round_summary(
    conversation: Conversation,
    *,
    memory_status: MemoryStatus | None = None,
) -> RoundSummary:
    return RoundSummary(
        conversation_id=conversation.id,
        persona=Persona(conversation.persona),
        mood=conversation.mood,
        letter=conversation.letter,
        status=cast(
            Literal["active", "closed", "pending_delete"],
            conversation.status,
        ),
        close_reason=conversation.close_reason,
        include_in_memory=conversation.include_in_memory,
        memory_status=memory_status,
        created_at=conversation.created_at.isoformat(),
        ended_at=conversation.ended_at.isoformat() if conversation.ended_at else None,
        deleted_at=conversation.deleted_at.isoformat()
        if conversation.deleted_at
        else None,
        purge_after=conversation.purge_after.isoformat()
        if conversation.purge_after
        else None,
    )


async def _round_summaries(
    session: AsyncSession,
    conversations: list[Conversation],
) -> list[RoundSummary]:
    statuses = await ConversationMemoryRepository(session).list_statuses(
        [conversation.id for conversation in conversations]
    )
    return [
        _round_summary(
            conversation,
            memory_status=cast(MemoryStatus | None, statuses.get(conversation.id)),
        )
        for conversation in conversations
    ]


def _round_message(message: Message) -> RoundMessage:
    return RoundMessage(
        role=cast(Literal["user", "assistant"], message.role),
        content=message.content,
        created_at=message.created_at.isoformat(),
    )


async def list_rounds(
    session: AsyncSession, external_user_id: str
) -> list[RoundSummary]:
    """列出指定外部用户已结束且未删除的轮次。"""
    user = await UserRepository(session).get_by_external_id(external_user_id)
    if user is None:
        return []
    conversations = await ConversationRepository(session).list_ended_for_user(user.id)
    return await _round_summaries(session, conversations)


async def list_deleted_rounds(
    session: AsyncSession,
    user_id: UUID,
) -> list[RoundSummary]:
    """列出回收站内容，供15天内恢复。"""
    conversations = await ConversationRepository(session).list_deleted_for_user(user_id)
    return await _round_summaries(session, conversations)


async def get_round_messages(
    session: AsyncSession,
    external_user_id: str,
    conversation_id: UUID,
) -> list[RoundMessage]:
    """返回某一轮的完整消息；不存在、不属于用户或已删除时返回 404。"""
    user = await UserRepository(session).get_by_external_id(external_user_id)
    conversation = (
        await ConversationRepository(session).get_for_user(conversation_id, user.id)
        if user is not None
        else None
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="round not found")
    messages = await MessageRepository(session).list_all(conversation_id)
    return [_round_message(m) for m in messages]


async def import_current_conversation(
    session: AsyncSession,
    user_id: UUID,
    request: ImportConversationRequest,
) -> UUID:
    """幂等导入游客当前会话，并在同一事务内执行七轮上限。"""
    users = UserRepository(session)
    conversations = ConversationRepository(session)
    messages = MessageRepository(session)
    try:
        user = await users.get_by_id(user_id, for_update=True)
        if user is None or not user.data_consent:
            raise HTTPException(status_code=403, detail="data consent required")

        existing = await conversations.get_by_client_session(
            user_id,
            request.client_session_id,
        )
        if existing is not None:
            return existing.id

        conversation = await conversations.create(
            user_id=user_id,
            persona=request.persona.value,
            client_session_id=request.client_session_id,
        )
        for message in request.messages:
            await messages.create(
                conversation_id=conversation.id,
                role=message.role,
                content=message.content,
            )
        await conversations.trim_for_user(
            user_id,
            keep=settings.free_conversation_limit,
            preserve_conversation_id=conversation.id,
        )
        await session.commit()
        return conversation.id
    except Exception:
        await session.rollback()
        raise


async def close_round(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
    *,
    reason: Literal["user_end", "browser_close"],
) -> RoundSummary:
    conversations = ConversationRepository(session)
    conversation = await conversations.get_for_user(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="round not found")
    await conversations.close(conversation, reason=reason)
    await session.commit()
    return _round_summary(conversation)


async def delete_round(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    conversations = ConversationRepository(session)
    conversation = await conversations.get_for_user(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="round not found")
    purge_after = datetime.now(UTC) + timedelta(
        days=settings.conversation_delete_retention_days
    )
    await conversations.mark_deleted(conversation, purge_after=purge_after)
    await session.commit()


async def restore_round(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
) -> RoundSummary:
    users = UserRepository(session)
    conversations = ConversationRepository(session)
    try:
        user = await users.get_by_id(user_id, for_update=True)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        conversation = await conversations.get_for_user(
            conversation_id,
            user_id,
            include_deleted=True,
        )
        if conversation is None or conversation.status != "pending_delete":
            raise HTTPException(status_code=404, detail="deleted round not found")
        await conversations.restore(conversation)
        await conversations.trim_for_user(
            user_id,
            keep=settings.free_conversation_limit,
            preserve_conversation_id=conversation.id,
        )
        await session.commit()
        return _round_summary(conversation)
    except Exception:
        await session.rollback()
        raise
