"""GET /v1/conversation/rounds —— "查看历史轮次"：列表 + 某一轮的完整消息。

只读接口，归属校验同项目其它地方一样靠 external_user_id 比对（见
history_service 顶部注释）。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.conversation.history_service import get_round_messages, list_rounds
from app.domain.conversation.schemas import RoundMessage, RoundSummary
from app.infra.database import get_db_session

router = APIRouter(prefix="/conversation", tags=["conversation"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/rounds", response_model=list[RoundSummary])
async def get_rounds(
    session: DatabaseSession,
    external_user_id: str = Query(..., min_length=1, max_length=128),
) -> list[RoundSummary]:
    return await list_rounds(session, external_user_id)


@router.get("/rounds/{conversation_id}/messages", response_model=list[RoundMessage])
async def get_round_messages_endpoint(
    conversation_id: UUID,
    session: DatabaseSession,
    external_user_id: str = Query(..., min_length=1, max_length=128),
) -> list[RoundMessage]:
    return await get_round_messages(session, external_user_id, conversation_id)
