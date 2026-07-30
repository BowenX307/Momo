"""GET /v1/conversation/rounds —— "查看历史轮次"：列表 + 某一轮的完整消息。

[2026-07-29] 接上登录态校验。原先这两个只读接口只看 query 里的 external_user_id，
不做任何验证——给一个 ID 字符串就返回那个人全部已结束的对话轮次、每一句消息、情绪
标记和 aftercare 回信。这是本项目里最敏感的数据，而 external_user_id 是前端自己生成、
在每个请求里明文传输、也会出现在 nginx 日志与浏览器历史里的字符串，等于可被冒用。

现在带了有效 token 的请求以 token 身份为准（`resolve_owner_id`），因此登录用户无法被
冒名读取。匿名请求维持原行为——登录态与匿名态并存是 58db4a0 的既有设计，匿名用户没有
token 但仍要能看自己的历史，所以不能一律 401。匿名侧的可伪造问题仍未解决，是否强制
登录属于产品决定（见 SECURITY-DEBT 笔记与本次 PR 里的提问）。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import OptionalAuthUserId, resolve_owner_id
from app.domain.conversation.history_service import get_round_messages, list_rounds
from app.domain.conversation.schemas import RoundMessage, RoundSummary
from app.infra.database import get_db_session

router = APIRouter(prefix="/conversation", tags=["conversation"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/rounds", response_model=list[RoundSummary])
async def get_rounds(
    session: DatabaseSession,
    verified_user_id: OptionalAuthUserId,
    external_user_id: str = Query(..., min_length=1, max_length=128),
) -> list[RoundSummary]:
    owner_id = resolve_owner_id(verified_user_id, external_user_id)
    return await list_rounds(session, owner_id)


@router.get("/rounds/{conversation_id}/messages", response_model=list[RoundMessage])
async def get_round_messages_endpoint(
    conversation_id: UUID,
    session: DatabaseSession,
    verified_user_id: OptionalAuthUserId,
    external_user_id: str = Query(..., min_length=1, max_length=128),
) -> list[RoundMessage]:
    owner_id = resolve_owner_id(verified_user_id, external_user_id)
    return await get_round_messages(session, owner_id, conversation_id)
