"""POST /v1/chat/demo —— 下周五 demo 的唯一对话入口。

只做：参数校验 → 取 provider 与 classifier → 调 service。具体 safety/分类/对话编排在
`app.domain.conversation.service.handle_chat_demo` 里。
"""

from fastapi import APIRouter

from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse
from app.domain.conversation.service import handle_chat_demo
from app.llm.factory import get_llm_provider, get_scene_classifier

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/demo", response_model=ChatDemoResponse)
async def chat_demo(request: ChatDemoRequest) -> ChatDemoResponse:
    provider, is_mock = get_llm_provider()
    classifier = get_scene_classifier()
    return await handle_chat_demo(
        request,
        provider=provider,
        classifier=classifier,
        is_mock=is_mock,
    )
