"""会话编排：safety → 场景分流 → llm 对话 → 拼装响应。

刻意不在这里碰数据库、记忆、人格卡，下周五 demo 只串通这一条链路。
单元测试通过传入 fake provider / classifier 来覆盖该模块（避免真调 LLM）。

降级策略：
- safety 命中危机：直接固定文案，**不**进 LLM，也不浪费一次分类调用；
- scene 缺省 + 分类失败：classifier 内部会兜底为 `loneliness`，service 层不感知；
- LLM 对话抛 `LLMError`（超时/网络/非 200/解析失败）：降级到 `MockProvider`，
  响应里 `degraded=True` + `is_mock=True`，便于前端弹"临时离线"提示、
  也便于演示时一眼看出上游出问题。

scene 路由：
- 前端只在每个会话第一句传 `scene=None`，后续把响应里返回的 scene 传回，
  避免每轮都跑一次分类（多 1 次 LLM 调用 ≈ 多花 50% token 与延迟）。
"""

from uuid import uuid4

import structlog

from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse, Scene
from app.domain.safety import check as safety_check
from app.llm.classifier import SceneClassifier
from app.llm.provider import LLMError, LLMProvider, MockProvider

logger = structlog.get_logger(__name__)


async def handle_chat_demo(
    request: ChatDemoRequest,
    provider: LLMProvider,
    classifier: SceneClassifier,
    is_mock: bool,
) -> ChatDemoResponse:
    """处理一次 demo 对话。

    Args:
        request: 入参（user_text + 可选 scene + history）。
        provider: 由 `factory.get_llm_provider()` 注入的对话 provider。
        classifier: 由 `factory.get_scene_classifier()` 注入的场景分类器。
        is_mock: provider 是否为 MockProvider，透传到响应里便于演示。
    """
    request_id = uuid4().hex

    safety = safety_check(request.user_text)
    if not safety.allowed:
        # safety 命中：用前端传的 scene 或默认 loneliness 透回；不调用 classifier。
        scene = request.scene or Scene.LONELINESS
        logger.info(
            "chat_demo_safety_fallback",
            request_id=request_id,
            scene=scene.value,
            reason=safety.reason,
        )
        return ChatDemoResponse(
            reply=safety.fallback_text,
            scene=scene,
            safety_flag=safety.reason,
            is_mock=is_mock,
            request_id=request_id,
        )

    if request.scene is None:
        scene = await classifier.classify(request.user_text)
        logger.info(
            "chat_demo_scene_classified",
            request_id=request_id,
            scene=scene.value,
        )
    else:
        scene = request.scene

    history = (
        [{"role": m.role, "content": m.content} for m in request.history]
        if request.history
        else None
    )

    try:
        reply = await provider.complete(
            scene=scene.value, user_text=request.user_text, history=history
        )
        logger.info(
            "chat_demo_ok",
            request_id=request_id,
            scene=scene.value,
            is_mock=is_mock,
            reply_chars=len(reply),
        )
        return ChatDemoResponse(
            reply=reply,
            scene=scene,
            safety_flag="ok",
            is_mock=is_mock,
            request_id=request_id,
        )
    except LLMError as exc:
        logger.warning(
            "chat_demo_llm_failed_degrading_to_mock",
            request_id=request_id,
            scene=scene.value,
            error_code=exc.code,
            upstream_status=exc.upstream_status,
        )
        mock_reply = await MockProvider().complete(
            scene=scene.value, user_text=request.user_text, history=history
        )
        return ChatDemoResponse(
            reply=mock_reply,
            scene=scene,
            safety_flag="ok",
            is_mock=True,
            request_id=request_id,
            degraded=True,
        )
