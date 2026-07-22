"""POST /v1/chat/demo —— Demo 对话入口。

负责参数校验、依赖装配和数据库会话注入；具体编排在 conversation service 中。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse
from app.domain.conversation.service import handle_chat_demo, stream_chat_demo
from app.domain.safety.factory import get_safety_provider
from app.infra.conversation_persistence import PostgresConversationPersistence
from app.infra.database import get_db_session
from app.llm.factory import get_llm_provider, get_scene_classifier
from app.tts.factory import get_tts_provider

router = APIRouter(prefix="/chat", tags=["chat"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/demo", response_model=ChatDemoResponse)
async def chat_demo(
    request: ChatDemoRequest,
    session: DatabaseSession,
) -> ChatDemoResponse:
    safety_provider, _ = get_safety_provider()
    provider, is_mock = get_llm_provider()
    classifier = get_scene_classifier()
    tts_provider, tts_is_mock = get_tts_provider()
    persistence = (
        PostgresConversationPersistence(session) if request.external_user_id else None
    )
    return await handle_chat_demo(
        request,
        safety_provider=safety_provider,
        provider=provider,
        classifier=classifier,
        is_mock=is_mock,
        tts_provider=tts_provider,
        tts_is_mock=tts_is_mock,
        persistence=persistence,
    )


@router.post("/demo/stream")
async def chat_demo_stream(
    request: ChatDemoRequest,
    session: DatabaseSession,
) -> StreamingResponse:
    safety_provider, _ = get_safety_provider()
    provider, is_mock = get_llm_provider()
    classifier = get_scene_classifier()
    tts_provider, tts_is_mock = get_tts_provider()
    persistence = (
        PostgresConversationPersistence(session) if request.external_user_id else None
    )
    return StreamingResponse(
        stream_chat_demo(
            request,
            safety_provider=safety_provider,
            provider=provider,
            classifier=classifier,
            tts_provider=tts_provider,
            tts_is_mock=tts_is_mock,
            is_mock=is_mock,
            persistence=persistence,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
