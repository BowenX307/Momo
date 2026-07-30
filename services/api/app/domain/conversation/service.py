"""会话编排：safety → 场景分流 → llm 对话 → 拼装响应。

数据库持久化通过可选接口注入；未提供匿名用户标识时保持无状态行为。
单元测试通过 fake provider / classifier / persistence 覆盖该模块，避免真实网络调用。

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

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import structlog

from app.domain.conversation.schemas import (
    ChatDemoRequest,
    ChatDemoResponse,
    HistoryMessage,
    Scene,
)
from app.domain.conversation.persistence import ConversationPersistence
from app.domain.reaction.service import detect_reaction
from app.domain.safety import SafetyReason
from app.domain.safety.provider import SafetyProvider
from app.domain.speech.service import _clean_for_tts
from app.llm.classifier import SceneClassifier
from app.llm.provider import LLMError, LLMProvider, MockProvider
from app.tts.provider import TTSError, TTSProvider

_SENTENCE_ENDS = frozenset("。？！…\n")

logger = structlog.get_logger(__name__)

# [2026-07-29] 服务端 history 字符预算。schemas 那边的 max_length=200 只挡住条数，
# 200 条 × 2000 字符仍有 40 万字符可以进模型，所以这里再按字符总量收一道——
# 这一层才是真正的成本控制，条数上限只负责挡掉明显异常的请求。
# 24000 字符对真实会话非常宽松（本产品单条通常一两百字），正常用户不会触发。
_MAX_HISTORY_CHARS = 24_000


def _build_history(messages: list[HistoryMessage]) -> list[dict] | None:
    """转成 provider 需要的格式，并按字符预算从最近往前保留。

    [2026-07-29] 原实现是 `[{...} for m in request.history]` 直接原样转发，
    中间没有任何截断或预算控制。history 由客户端提供且不可信——绕过前端直接
    发请求就能塞进任意多历史，全部计入 DeepSeek 账单，且 safety 层只检查
    user_text 不检查 history。

    截断放在服务端而不是前端：前端的限制可以被绕过，这里不行。
    丢弃从最早的消息开始，保住最近的上下文（对话连贯性影响最小）。
    """
    if not messages:
        return None

    kept: list[dict] = []
    remaining = _MAX_HISTORY_CHARS
    for message in reversed(messages):
        remaining -= len(message.content)
        if remaining < 0:
            break
        kept.append({"role": message.role, "content": message.content})
    kept.reverse()

    dropped = len(messages) - len(kept)
    if dropped:
        logger.info(
            "chat_history_truncated",
            received=len(messages),
            kept=len(kept),
            dropped=dropped,
            budget_chars=_MAX_HISTORY_CHARS,
        )
    return kept or None


async def _detect_emotion_safe(user_text: str, provider: LLMProvider) -> str:
    """调用 provider.detect_emotion，任何异常都静默返回空串。"""
    detect = getattr(provider, "detect_emotion", None)
    if detect is None:
        return ""
    try:
        return await detect(user_text)
    except Exception:
        return ""


async def _synthesize_audio(
    reply: str,
    scene: Scene,
    tts_provider: TTSProvider,
    tts_is_mock: bool,
    request_id: str,
    persona: str | None = None,
) -> tuple[str, str, bool]:
    """调用 TTS，返回 (audio_base64, content_type, is_mock)。失败时静默降级返回空音频。"""
    try:
        result = await tts_provider.synthesize(
            _clean_for_tts(reply), scene=scene.value, persona=persona
        )
        audio_b64 = (
            base64.b64encode(result.audio).decode("ascii") if result.audio else ""
        )
        return audio_b64, result.content_type, tts_is_mock
    except TTSError as exc:
        logger.warning(
            "chat_demo_tts_failed",
            request_id=request_id,
            error_code=exc.code,
            error_message=str(exc),
        )
        return "", "audio/mpeg", True


async def _persist_exchange_safe(
    persistence: ConversationPersistence | None,
    request: ChatDemoRequest,
    *,
    scene: Scene,
    reply: str,
    safety_flag: SafetyReason,
    emotion: str,
    request_id: str,
    is_mock: bool,
    degraded: bool,
) -> UUID | None:
    """保存一轮对话；数据库异常只记录日志，不中断用户回复。"""
    if persistence is None or request.external_user_id is None:
        return request.conversation_id

    try:
        return await persistence.save_exchange(
            external_user_id=request.external_user_id,
            conversation_id=request.conversation_id,
            scene=scene.value,
            persona=request.persona.value,
            user_text=request.user_text,
            reply=reply,
            safety_flag=safety_flag,
            emotion=emotion,
            request_id=request_id,
            is_mock=is_mock,
            degraded=degraded,
        )
    except Exception:
        logger.exception(
            "chat_demo_persistence_failed",
            request_id=request_id,
            conversation_id=str(request.conversation_id or ""),
        )
        return request.conversation_id


async def handle_chat_demo(
    request: ChatDemoRequest,
    safety_provider: SafetyProvider,
    provider: LLMProvider,
    classifier: SceneClassifier,
    is_mock: bool,
    tts_provider: TTSProvider | None = None,
    tts_is_mock: bool = True,
    persistence: ConversationPersistence | None = None,
) -> ChatDemoResponse:
    """处理一次 demo 对话。

    Args:
        request: 入参（user_text + 可选 scene + history）。
        provider: 由 `factory.get_llm_provider()` 注入的对话 provider。
        classifier: 由 `factory.get_scene_classifier()` 注入的场景分类器。
        is_mock: provider 是否为 MockProvider，透传到响应里便于演示。
    """
    request_id = uuid4().hex

    safety = await safety_provider.check(request.user_text)
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
                safety.fallback_text,
                scene,
                tts_provider,
                tts_is_mock,
                request_id,
                persona=request.persona.value,
            )
        conversation_id = await _persist_exchange_safe(
            persistence,
            request,
            scene=scene,
            reply=safety.fallback_text,
            safety_flag=safety.reason,
            emotion="",
            request_id=request_id,
            is_mock=is_mock,
            degraded=False,
        )
        return ChatDemoResponse(
            reply=safety.fallback_text,
            scene=scene,
            safety_flag=safety.reason,
            is_mock=is_mock,
            request_id=request_id,
            conversation_id=conversation_id,
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

    history = _build_history(request.history)

    try:
        reply, emotion = await asyncio.gather(
            provider.complete(
                scene=scene.value,
                user_text=request.user_text,
                history=history,
                persona=request.persona.value,
            ),
            _detect_emotion_safe(request.user_text, provider),
        )
        logger.info(
            "chat_demo_ok",
            request_id=request_id,
            scene=scene.value,
            persona=request.persona.value,
            is_mock=is_mock,
            reply_chars=len(reply),
            emotion=emotion,
        )
        # 反应判断需要 reply，和 TTS 并行跑，藏在合成时间里，几乎不增加等待
        reaction_task = asyncio.create_task(
            detect_reaction(reply, request.persona.value)
        )
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                reply,
                scene,
                tts_provider,
                tts_is_mock,
                request_id,
                persona=request.persona.value,
            )
        reaction = await reaction_task
        conversation_id = await _persist_exchange_safe(
            persistence,
            request,
            scene=scene,
            reply=reply,
            safety_flag="ok",
            emotion=emotion,
            request_id=request_id,
            is_mock=is_mock,
            degraded=False,
        )
        return ChatDemoResponse(
            reply=reply,
            scene=scene,
            safety_flag="ok",
            is_mock=is_mock,
            request_id=request_id,
            conversation_id=conversation_id,
            audio_base64=audio_b64,
            audio_content_type=audio_ct,
            audio_is_mock=audio_mock,
            emotion=emotion,
            reaction=reaction,
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
            scene=scene.value,
            user_text=request.user_text,
            history=history,
            persona=request.persona.value,
        )
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                mock_reply,
                scene,
                tts_provider,
                tts_is_mock,
                request_id,
                persona=request.persona.value,
            )
        conversation_id = await _persist_exchange_safe(
            persistence,
            request,
            scene=scene,
            reply=mock_reply,
            safety_flag="ok",
            emotion="",
            request_id=request_id,
            is_mock=True,
            degraded=True,
        )
        return ChatDemoResponse(
            reply=mock_reply,
            scene=scene,
            safety_flag="ok",
            is_mock=True,
            request_id=request_id,
            conversation_id=conversation_id,
            degraded=True,
            audio_base64=audio_b64,
            audio_content_type=audio_ct,
            audio_is_mock=audio_mock,
        )


async def _iter_sentences(
    token_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """把 token 流按句子边界切分，每完整一句 yield 一次。

    只按整句切分。曾有"第一段在逗号处抢跑切出"的首字加速,因为会把半句话
    切成两段音频、衔接处顿挫明显,2026-07-17 按产品实听反馈移除。
    """
    buf = ""
    async for token in token_stream:
        buf += token
        if buf[-1] in _SENTENCE_ENDS:
            chunk = buf.strip()
            if chunk:
                yield chunk
            buf = ""
    if buf.strip():
        yield buf.strip()


async def stream_chat_demo(
    request: ChatDemoRequest,
    safety_provider: SafetyProvider,
    provider: LLMProvider,
    classifier: SceneClassifier,
    tts_provider: TTSProvider | None,
    tts_is_mock: bool,
    is_mock: bool,
    persistence: ConversationPersistence | None = None,
) -> AsyncGenerator[str, None]:
    """流式版本：LLM 逐句输出，每句完成立刻 TTS，以 SSE data 行 yield。"""
    request_id = uuid4().hex

    safety = await safety_provider.check(request.user_text)
    if not safety.allowed:
        scene = request.scene or Scene.LONELINESS
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                safety.fallback_text,
                scene,
                tts_provider,
                tts_is_mock,
                request_id,
                persona=request.persona.value,
            )
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "audio",
                    "index": 0,
                    "audio_base64": audio_b64,
                    "content_type": audio_ct,
                    "is_mock": audio_mock,
                }
            )
            + "\n\n"
        )
        conversation_id = await _persist_exchange_safe(
            persistence,
            request,
            scene=scene,
            reply=safety.fallback_text,
            safety_flag=safety.reason,
            emotion="",
            request_id=request_id,
            is_mock=is_mock,
            degraded=False,
        )
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "done",
                    "reply": safety.fallback_text,
                    "scene": scene.value,
                    "safety_flag": safety.reason,
                    "is_mock": False,
                    "request_id": request_id,
                    "conversation_id": str(conversation_id)
                    if conversation_id
                    else None,
                    "degraded": False,
                }
            )
            + "\n\n"
        )
        return

    if request.scene is None:
        scene = await classifier.classify(request.user_text)
    else:
        scene = request.scene

    history = _build_history(request.history)

    emotion_task = asyncio.create_task(
        _detect_emotion_safe(request.user_text, provider)
    )

    full_reply = ""
    sentence_idx = 0
    response_is_mock = is_mock
    degraded = False

    try:
        token_stream = provider.stream_complete(  # type: ignore[attr-defined]
            scene=scene.value,
            user_text=request.user_text,
            history=history,
            persona=request.persona.value,
        )
        async for sentence in _iter_sentences(token_stream):
            full_reply += sentence
            audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
            if tts_provider:
                audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                    sentence,
                    scene,
                    tts_provider,
                    tts_is_mock,
                    request_id,
                    persona=request.persona.value,
                )
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "audio",
                        "index": sentence_idx,
                        "text": sentence,
                        "audio_base64": audio_b64,
                        "content_type": audio_ct,
                        "is_mock": audio_mock,
                    }
                )
                + "\n\n"
            )
            sentence_idx += 1

    except (LLMError, AttributeError):
        # provider 不支持流式（如 Mock）：降级到一次性调用
        try:
            full_reply = await provider.complete(
                scene=scene.value,
                user_text=request.user_text,
                history=history,
                persona=request.persona.value,
            )
        except LLMError:
            full_reply = await MockProvider().complete(
                scene=scene.value,
                user_text=request.user_text,
                history=history,
                persona=request.persona.value,
            )
            response_is_mock = True
            degraded = True
        audio_b64, audio_ct, audio_mock = ("", "audio/mpeg", True)
        if tts_provider:
            audio_b64, audio_ct, audio_mock = await _synthesize_audio(
                full_reply,
                scene,
                tts_provider,
                tts_is_mock,
                request_id,
                persona=request.persona.value,
            )
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "audio",
                    "index": 0,
                    "text": full_reply,
                    "audio_base64": audio_b64,
                    "content_type": audio_ct,
                    "is_mock": audio_mock,
                }
            )
            + "\n\n"
        )

    emotion = await emotion_task
    conversation_id = await _persist_exchange_safe(
        persistence,
        request,
        scene=scene,
        reply=full_reply,
        safety_flag="ok",
        emotion=emotion,
        request_id=request_id,
        is_mock=response_is_mock,
        degraded=degraded,
    )
    yield (
        "data: "
        + json.dumps(
            {
                "type": "done",
                "reply": full_reply,
                "scene": scene.value,
                "safety_flag": "ok",
                "is_mock": response_is_mock,
                "request_id": request_id,
                "conversation_id": str(conversation_id) if conversation_id else None,
                "degraded": degraded,
                "emotion": emotion,
            }
        )
        + "\n\n"
    )
