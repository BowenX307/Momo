"""登录用户的历史轮次导入、查看、结束、删除与恢复接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.deps import OptionalAuthUserId, resolve_owner_id
from app.domain.conversation.history_service import (
    close_round,
    delete_round,
    get_round_messages,
    import_current_conversation,
    list_deleted_rounds,
    list_rounds,
    restore_round,
)
from app.domain.conversation.memory_service import set_memory_selection
from app.domain.conversation.schemas import (
    CloseConversationRequest,
    ImportConversationRequest,
    ImportConversationResponse,
    MemorySelectionRequest,
    MemorySelectionResponse,
    RoundMessage,
    RoundSummary,
)
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


@router.get("/rounds/deleted", response_model=list[RoundSummary])
async def get_deleted_rounds(
    session: DatabaseSession,
    user: CurrentUser,
) -> list[RoundSummary]:
    return await list_deleted_rounds(session, user.id)


@router.get("/rounds/{conversation_id}/messages", response_model=list[RoundMessage])
async def get_round_messages_endpoint(
    conversation_id: UUID,
    session: DatabaseSession,
    verified_user_id: OptionalAuthUserId,
    external_user_id: str = Query(..., min_length=1, max_length=128),
) -> list[RoundMessage]:
    owner_id = resolve_owner_id(verified_user_id, external_user_id)
    return await get_round_messages(session, owner_id, conversation_id)


@router.post("/import-current", response_model=ImportConversationResponse)
async def import_current(
    request: ImportConversationRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> ImportConversationResponse:
    conversation_id = await import_current_conversation(session, user.id, request)
    return ImportConversationResponse(conversation_id=conversation_id)


@router.post("/rounds/{conversation_id}/close", response_model=RoundSummary)
async def close_round_endpoint(
    conversation_id: UUID,
    request: CloseConversationRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> RoundSummary:
    return await close_round(
        session,
        user.id,
        conversation_id,
        reason=request.reason,
    )


@router.delete("/rounds/{conversation_id}", status_code=204)
async def delete_round_endpoint(
    conversation_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> None:
    await delete_round(session, user.id, conversation_id)


@router.post("/rounds/{conversation_id}/restore", response_model=RoundSummary)
async def restore_round_endpoint(
    conversation_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> RoundSummary:
    return await restore_round(session, user.id, conversation_id)


@router.patch(
    "/rounds/{conversation_id}/memory",
    response_model=MemorySelectionResponse,
)
async def select_round_memory(
    conversation_id: UUID,
    request: MemorySelectionRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> MemorySelectionResponse:
    return await set_memory_selection(
        session,
        user.id,
        conversation_id,
        enabled=request.enabled,
    )
