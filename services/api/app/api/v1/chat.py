"""POST /v1/chat/demo —— Demo 对话入口。

负责参数校验、依赖装配和数据库会话注入；具体编排在 conversation service 中。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import RedisDep, enforce_rate_limit
from app.api.dependencies import OptionalCurrentUser
from app.core.config import settings
from app.domain.conversation.memory_service import get_memory_context
from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse
from app.domain.conversation.service import handle_chat_demo, stream_chat_demo
from app.domain.safety.factory import get_safety_provider
from app.infra.conversation_persistence import PostgresConversationPersistence
from app.infra.database import get_db_session
from app.llm.factory import get_llm_provider
from app.tts.factory import get_tts_provider

router = APIRouter(prefix="/chat", tags=["chat"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _get_persistence(
    session: AsyncSession,
    user: OptionalCurrentUser,
) -> PostgresConversationPersistence | None:
    """只有已登录并授权的用户才启用 PostgreSQL 持久化。"""
    if not settings.persistence_enabled or user is None or not user.data_consent:
        return None
    return PostgresConversationPersistence(session, user_id=user.id)


@router.post("/demo", response_model=ChatDemoResponse)
async def chat_demo(
    request: ChatDemoRequest,
    session: DatabaseSession,
    http_request: Request,
    redis: RedisDep,
    user: OptionalCurrentUser,
) -> ChatDemoResponse:
    await enforce_rate_limit(
        http_request,
        redis,
        bucket="chat",
        limit=settings.rate_limit_chat_per_minute,
        identity=request.external_user_id,
    )
    safety_provider, _ = get_safety_provider()
    provider, is_mock = get_llm_provider()
    tts_provider, tts_is_mock = get_tts_provider()
    persistence = _get_persistence(session, user)
    memory_context = (
        await get_memory_context(session, user.id)
        if user is not None and user.data_consent
        else ""
    )
    return await handle_chat_demo(
        request,
        safety_provider=safety_provider,
        provider=provider,
        is_mock=is_mock,
        tts_provider=tts_provider,
        tts_is_mock=tts_is_mock,
        persistence=persistence,
        memory_context=memory_context,
    )


@router.post("/demo/stream")
async def chat_demo_stream(
    request: ChatDemoRequest,
    session: DatabaseSession,
    http_request: Request,
    redis: RedisDep,
    user: OptionalCurrentUser,
) -> StreamingResponse:
    await enforce_rate_limit(
        http_request,
        redis,
        bucket="chat",
        limit=settings.rate_limit_chat_per_minute,
        identity=request.external_user_id,
    )
    safety_provider, _ = get_safety_provider()
    provider, is_mock = get_llm_provider()
    tts_provider, tts_is_mock = get_tts_provider()
    persistence = _get_persistence(session, user)
    memory_context = (
        await get_memory_context(session, user.id)
        if user is not None and user.data_consent
        else ""
    )
    return StreamingResponse(
        stream_chat_demo(
            request,
            safety_provider=safety_provider,
            provider=provider,
            tts_provider=tts_provider,
            tts_is_mock=tts_is_mock,
            is_mock=is_mock,
            persistence=persistence,
            memory_context=memory_context,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
