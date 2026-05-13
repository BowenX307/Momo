"""会话编排：safety → llm → 拼装响应。

刻意不在这里碰数据库、记忆、人格卡，下周五 demo 只串通这一条链路。
单元测试通过传入 fake provider 来覆盖该模块（避免真调 LLM）。

降级策略：
- safety 命中危机：直接固定文案，**不**进 LLM；
- LLM 调用抛 `LLMError`（超时/网络/非 200/解析失败）：降级到 `MockProvider`，
  响应里 `degraded=True` + `is_mock=True`，便于前端弹"临时离线"提示、
  也便于演示时一眼看出上游出问题。
"""

from uuid import uuid4

import structlog

from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse
from app.domain.safety import check as safety_check
from app.llm.provider import LLMError, LLMProvider, MockProvider

logger = structlog.get_logger(__name__)


async def handle_chat_demo(
    request: ChatDemoRequest,
    provider: LLMProvider,
    is_mock: bool,
) -> ChatDemoResponse:
    """处理一次 demo 对话。

    Args:
        request: 入参（user_text + scene）。
        provider: 由 `app.llm.factory.get_llm_provider()` 注入的 provider。
        is_mock: provider 是否为 MockProvider，透传到响应里便于演示。
    """
    request_id = uuid4().hex

    safety = safety_check(request.user_text)
    if not safety.allowed:
        logger.info(
            "chat_demo_safety_fallback",
            request_id=request_id,
            scene=request.scene.value,
            reason=safety.reason,
        )
        return ChatDemoResponse(
            reply=safety.fallback_text,
            scene=request.scene,
            safety_flag=safety.reason,
            is_mock=is_mock,
            request_id=request_id,
        )

    try:
        reply = await provider.complete(
            scene=request.scene.value, user_text=request.user_text
        )
        logger.info(
            "chat_demo_ok",
            request_id=request_id,
            scene=request.scene.value,
            is_mock=is_mock,
            reply_chars=len(reply),
        )
        return ChatDemoResponse(
            reply=reply,
            scene=request.scene,
            safety_flag="ok",
            is_mock=is_mock,
            request_id=request_id,
        )
    except LLMError as exc:
        logger.warning(
            "chat_demo_llm_failed_degrading_to_mock",
            request_id=request_id,
            scene=request.scene.value,
            error_code=exc.code,
            upstream_status=exc.upstream_status,
        )
        mock_reply = await MockProvider().complete(
            scene=request.scene.value, user_text=request.user_text
        )
        return ChatDemoResponse(
            reply=mock_reply,
            scene=request.scene,
            safety_flag="ok",
            is_mock=True,
            request_id=request_id,
            degraded=True,
        )
