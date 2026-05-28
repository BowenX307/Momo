"""POST /v1/chat/demo —— 下周五 demo 的唯一对话入口。

只做：参数校验 → 取 provider 与 classifier → 调 service。具体 safety/分类/对话编排在
`app.domain.conversation.service.handle_chat_demo` 里。
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse
from app.domain.conversation.service import handle_chat_demo, stream_chat_demo
from app.llm.factory import get_llm_provider, get_scene_classifier
from app.tts.factory import get_tts_provider

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/demo", response_model=ChatDemoResponse)
async def chat_demo(request: ChatDemoRequest) -> ChatDemoResponse:
    provider, is_mock = get_llm_provider()
    classifier = get_scene_classifier()
    tts_provider, tts_is_mock = get_tts_provider()
    return await handle_chat_demo(
        request,
        provider=provider,
        classifier=classifier,
        is_mock=is_mock,
        tts_provider=tts_provider,
        tts_is_mock=tts_is_mock,
    )


@router.post("/demo/stream")
async def chat_demo_stream(request: ChatDemoRequest) -> StreamingResponse:
    provider, _ = get_llm_provider()
    classifier = get_scene_classifier()
    tts_provider, tts_is_mock = get_tts_provider()
    return StreamingResponse(
        stream_chat_demo(
            request,
            provider=provider,
            classifier=classifier,
            tts_provider=tts_provider,
            tts_is_mock=tts_is_mock,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
