""""查看历史轮次"的读取逻辑：列出某用户已结束的轮次 + 某一轮的完整消息。

归属校验方式和项目里其它地方一致：拿前端传的 external_user_id 去查 user，
再确认 conversation 属于这个 user——和现有信任模型一样，没有做真正的鉴权
（见 memory：external_id 可伪造是已知且暂不处理的安全债）。
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
