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

import base64
import json
from collections.abc import AsyncGenerator
from uuid import uuid4

import structlog

from app.domain.conversation.schemas import ChatDemoRequest, ChatDemoResponse, Persona, Scene
from app.domain.safety import check as safety_check
from app.domain.speech.service import _clean_for_tts
from app.llm.classifier import SceneClassifier
from app.llm.provider import LLMError, LLMProvider, MockProvider
from app.tts.provider import TTSError, TTSProvider

_SENTENCE_ENDS = frozenset("。？！…\n")

logger = structlog.get_logger(__name__)


async def _synthesize_audio(
    reply: str,
    scene: Scene,
    tts_provider: TTSProvider,
    tts_is_mock: bool,
    request_id: str,
) -> tuple[str, str, bool]:
    """调用 TTS，返回 (audio_base64, content_type, is_mock)。失败时静默降级返回空音频。"""
    try:
        result = await tts_provider.synthesize(_clean_for_tts(reply), scene=scene.value)
        audio_b64 = base64.b64encode(result.audio).decode("ascii") if result.audio else ""
        return audio_b64, result.content_type, tts_is_mock
    except TTSError as exc:
        logger.warning(
            "chat_demo_tts_failed",
            request_id=request_id,
            error_code=exc.code,
            error_message=str(exc),
        )
        return "", "audio/mpeg", True


async def handle_chat_demo(
    request: ChatDemoRequest,
    provider: LLMProvider,
    classifier: SceneClassifier,
    is_mock: bool,
    tts_provider: TTSProvider | None = None,
    tts_is_mock: bool = True,
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
        scene = request.scene or Scene.LONELINESS
        logger.info(
            "chat_demo_safety_fallback",
            request_id=request_id,
            scene=scene.value,
            reason=safety.reason,
        )
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                safety.fallback_text, scene, tts_provider, tts_is_mock, request_id
            )
        return ChatDemoResponse(
            reply=safety.fallback_text,
            scene=scene,
            safety_flag=safety.reason,
            is_mock=is_mock,
            request_id=request_id,
            audio_base64=audio_b64,
            audio_content_type=audio_ct,
            audio_is_mock=audio_mock,
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
            scene=scene.value, user_text=request.user_text, history=history,
            persona=request.persona.value,
        )
        logger.info(
            "chat_demo_ok",
            request_id=request_id,
            scene=scene.value,
            persona=request.persona.value,
            is_mock=is_mock,
            reply_chars=len(reply),
        )
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                reply, scene, tts_provider, tts_is_mock, request_id
            )
        return ChatDemoResponse(
            reply=reply,
            scene=scene,
            safety_flag="ok",
            is_mock=is_mock,
            request_id=request_id,
            audio_base64=audio_b64,
            audio_content_type=audio_ct,
            audio_is_mock=audio_mock,
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
            scene=scene.value, user_text=request.user_text, history=history,
            persona=request.persona.value,
        )
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                mock_reply, scene, tts_provider, tts_is_mock, request_id
            )
        return ChatDemoResponse(
            reply=mock_reply,
            scene=scene,
            safety_flag="ok",
            is_mock=True,
            request_id=request_id,
            degraded=True,
            audio_base64=audio_b64,
            audio_content_type=audio_ct,
            audio_is_mock=audio_mock,
        )


async def _iter_sentences(
    token_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """把 token 流按句子边界切分，每完整一句 yield 一次。"""
    buf = ""
    async for token in token_stream:
        buf += token
        if buf[-1] in _SENTENCE_ENDS:
            sentence = buf.strip()
            if sentence:
                yield sentence
            buf = ""
    if buf.strip():
        yield buf.strip()


async def stream_chat_demo(
    request: ChatDemoRequest,
    provider: LLMProvider,
    classifier: SceneClassifier,
    tts_provider: TTSProvider | None,
    tts_is_mock: bool,
) -> AsyncGenerator[str, None]:
    """流式版本：LLM 逐句输出，每句完成立刻 TTS，以 SSE data 行 yield。"""
    request_id = uuid4().hex

    safety = safety_check(request.user_text)
    if not safety.allowed:
        scene = request.scene or Scene.LONELINESS
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                safety.fallback_text, scene, tts_provider, tts_is_mock, request_id
            )
        yield "data: " + json.dumps({
            "type": "audio", "index": 0,
            "audio_base64": audio_b64, "content_type": audio_ct, "is_mock": audio_mock,
        }) + "\n\n"
        yield "data: " + json.dumps({
            "type": "done", "reply": safety.fallback_text, "scene": scene.value,
            "safety_flag": safety.reason, "is_mock": False,
            "request_id": request_id, "degraded": False,
        }) + "\n\n"
        return

    if request.scene is None:
        scene = await classifier.classify(request.user_text)
    else:
        scene = request.scene

    history = (
        [{"role": m.role, "content": m.content} for m in request.history]
        if request.history
        else None
    )

    full_reply = ""
    sentence_idx = 0

    try:
        token_stream = provider.stream_complete(  # type: ignore[attr-defined]
            scene=scene.value, user_text=request.user_text, history=history,
            persona=request.persona.value,
        )
        async for sentence in _iter_sentences(token_stream):
            full_reply += sentence
            audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
            if tts_provider:
                audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                    sentence, scene, tts_provider, tts_is_mock, request_id
                )
            yield "data: " + json.dumps({
                "type": "audio", "index": sentence_idx,
                "audio_base64": audio_b64, "content_type": audio_ct, "is_mock": audio_mock,
            }) + "\n\n"
            sentence_idx += 1

    except (LLMError, AttributeError):
        # provider 不支持流式（如 Mock）：降级到一次性调用
        try:
            full_reply = await provider.complete(
                scene=scene.value, user_text=request.user_text, history=history,
                persona=request.persona.value,
            )
        except LLMError:
            full_reply = await MockProvider().complete(
                scene=scene.value, user_text=request.user_text, history=history,
                persona=request.persona.value,
            )
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                full_reply, scene, tts_provider, tts_is_mock, request_id
            )
        yield "data: " + json.dumps({
            "type": "audio", "index": 0,
            "audio_base64": audio_b64, "content_type": audio_ct, "is_mock": audio_mock,
        }) + "\n\n"

    yield "data: " + json.dumps({
        "type": "done", "reply": full_reply, "scene": scene.value,
        "safety_flag": "ok", "is_mock": False,
        "request_id": request_id, "degraded": False,
    }) + "\n\n"
