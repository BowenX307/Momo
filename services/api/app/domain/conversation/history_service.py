""""查看历史轮次"的读取逻辑：列出某用户已结束的轮次 + 某一轮的完整消息。

归属校验：拿传入的 external_user_id 查 user，再确认 conversation 属于这个 user。

[2026-07-29] 这里收到的 external_user_id 已经过路由层的身份裁决（见
`app/api/v1/deps.py` 的 `resolve_owner_id`）：带有效 token 的请求会被换成 token 自己的
身份，所以登录用户无法被冒名读取。匿名请求仍然是「信任前端传的字符串」——那部分可伪造
的问题还在，是否强制登录属产品决定。本模块只负责按给定身份查数据，不重复做裁决。
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.conversation.schemas import RoundMessage, RoundSummary
from app.infra.models import Conversation, Message
from app.infra.repositories import ConversationRepository, MessageRepository, UserRepository


def _round_summary(conversation: Conversation) -> RoundSummary:
    return RoundSummary(
        conversation_id=conversation.id,
        persona=conversation.persona,
        scene=conversation.scene,
        mood=conversation.mood,
        letter=conversation.letter,
        created_at=conversation.created_at.isoformat(),
        ended_at=conversation.ended_at.isoformat(),
    )


def _round_message(message: Message) -> RoundMessage:
    return RoundMessage(
        role=message.role,
        content=message.content,
        created_at=message.created_at.isoformat(),
    )


async def list_rounds(session: AsyncSession, external_user_id: str) -> list[RoundSummary]:
    """列出该用户已结束归档的轮次；用户不存在（还没聊过）时返回空列表。"""
    user = await UserRepository(session).get_by_external_id(external_user_id)
    if user is None:
        return []
    conversations = await ConversationRepository(session).list_ended_for_user(user.id)
    return [_round_summary(c) for c in conversations]


async def get_round_messages(
    session: AsyncSession,
    external_user_id: str,
    conversation_id: UUID,
) -> list[RoundMessage]:
    """返回某一轮的完整消息；找不到（不存在/不属于该用户）时 404。"""
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
