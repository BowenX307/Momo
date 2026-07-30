"""会话编排单元测试。用假 provider / 假 classifier 覆盖各分支，不打真实网络。"""

from uuid import UUID

import pytest

from app.domain.conversation.schemas import ChatDemoRequest, HistoryMessage, Scene
from app.domain.conversation.service import (
    _MAX_HISTORY_CHARS,
    _build_history,
    handle_chat_demo,
)
from app.domain.safety import SafetyReason
from app.domain.safety.provider import LocalOnlySafetyProvider
from app.llm.classifier import SceneClassifier
from app.llm.provider import LLMError, LLMProvider


class _FakeOkProvider:
    async def complete(
        self,
        scene: str,
        user_text: str,
        history: list[dict] | None = None,
        persona: str = "nini",
    ) -> str:
        return f"fake-reply for {scene}: {user_text}"


class _FakeFailingProvider:
    def __init__(self, code: str = "http_status", status: int | None = 402) -> None:
        self.code = code
        self.status = status

    async def complete(
        self,
        scene: str,
        user_text: str,
        history: list[dict] | None = None,
        persona: str = "nini",
    ) -> str:
        raise LLMError(self.code, "boom", upstream_status=self.status)


class _SpyClassifier:
    """记录是否被调用，并按需返回固定 scene。用于验证 service 的分流分支。"""

    def __init__(self, return_scene: Scene = Scene.LATE_NIGHT) -> None:
        self.return_scene = return_scene
        self.call_count = 0
        self.last_text: str | None = None

    async def classify(self, user_text: str) -> Scene:
        self.call_count += 1
        self.last_text = user_text
        return self.return_scene


class _FakePersistence:
    """记录持久化参数，并返回固定会话 ID。"""

    conversation_id = UUID("00000000-0000-0000-0000-000000000123")

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def save_exchange(
        self,
        *,
        external_user_id: str,
        conversation_id: UUID | None,
        scene: str,
        persona: str,
        user_text: str,
        reply: str,
        safety_flag: SafetyReason,
        emotion: str,
        request_id: str,
        is_mock: bool,
        degraded: bool,
    ) -> UUID:
        self.calls.append(
            {
                "external_user_id": external_user_id,
                "conversation_id": conversation_id,
                "scene": scene,
                "persona": persona,
                "user_text": user_text,
                "reply": reply,
                "safety_flag": safety_flag,
                "emotion": emotion,
                "request_id": request_id,
                "is_mock": is_mock,
                "degraded": degraded,
            }
        )
        return self.conversation_id


@pytest.mark.asyncio
async def test_handle_chat_demo_uses_explicit_scene_and_skips_classifier():
    """前端传了 scene → service 必须直接用，不调用 classifier。"""
    provider: LLMProvider = _FakeOkProvider()
    classifier = _SpyClassifier()
    safety_provider = LocalOnlySafetyProvider()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="今晚胸口闷", scene=Scene.LATE_NIGHT),
        safety_provider=safety_provider,
        provider=provider,
        classifier=classifier,
        is_mock=False,
    )
    assert response.reply.startswith("fake-reply for late_night")
    assert response.scene == Scene.LATE_NIGHT
    assert classifier.call_count == 0  # 未调用分类器
    assert response.is_mock is False
    assert response.degraded is False


@pytest.mark.asyncio
async def test_handle_chat_demo_classifies_when_scene_omitted():
    """前端没传 scene → service 应调用 classifier，并把结果用到对话和响应里。"""
    provider: LLMProvider = _FakeOkProvider()
    classifier = _SpyClassifier(return_scene=Scene.RELATIONSHIP)
    safety_provider = LocalOnlySafetyProvider()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="他根本就不在乎我", scene=None),
        safety_provider=safety_provider,
        provider=provider,
        classifier=classifier,
        is_mock=False,
    )
    assert classifier.call_count == 1
    assert classifier.last_text == "他根本就不在乎我"
    assert response.scene == Scene.RELATIONSHIP
    assert response.reply.startswith("fake-reply for relationship")


@pytest.mark.asyncio
async def test_handle_chat_demo_degrades_to_mock_on_llm_error():
    """对话 provider 抛 LLMError → 降级到 MockProvider，degraded=True，scene 保留。"""
    provider: LLMProvider = _FakeFailingProvider(code="http_status", status=402)
    classifier: SceneClassifier = _SpyClassifier()
    safety_provider = LocalOnlySafetyProvider()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="今晚胸口闷", scene=Scene.LATE_NIGHT),
        safety_provider=safety_provider,
        provider=provider,
        classifier=classifier,
        is_mock=False,
    )
    assert response.degraded is True
    assert response.is_mock is True
    assert response.scene == Scene.LATE_NIGHT
    assert response.safety_flag == "ok"
    assert response.reply  # MockProvider 必须给出可渲染回复


@pytest.mark.asyncio
async def test_handle_chat_demo_safety_blocks_before_llm_and_classifier():
    """危机关键词 → 直接固定文案，**既不调用 provider 也不调用 classifier**。"""
    provider: LLMProvider = _FakeFailingProvider()
    classifier = _SpyClassifier()
    safety_provider = LocalOnlySafetyProvider()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="我想自杀", scene=None),
        safety_provider=safety_provider,
        provider=provider,
        classifier=classifier,
        is_mock=False,
    )
    assert response.safety_flag == "crisis_keyword"
    assert response.degraded is False
    assert classifier.call_count == 0  # safety 路径不应浪费一次分类调用
    assert response.scene == Scene.LONELINESS  # safety + scene=None → 默认 loneliness
    assert "诊断" not in response.reply
    assert "治疗" not in response.reply


@pytest.mark.asyncio
async def test_handle_chat_demo_persists_normal_exchange():
    """带匿名用户标识时，正常回复应保存并返回会话 ID。"""
    persistence = _FakePersistence()
    response = await handle_chat_demo(
        ChatDemoRequest(
            user_text="今天压力很大",
            external_user_id="browser-user-1",
            scene=Scene.STRESS,
        ),
        safety_provider=LocalOnlySafetyProvider(),
        provider=_FakeOkProvider(),
        classifier=_SpyClassifier(),
        is_mock=False,
        persistence=persistence,
    )

    assert response.conversation_id == persistence.conversation_id
    assert len(persistence.calls) == 1
    assert persistence.calls[0]["user_text"] == "今天压力很大"
    assert persistence.calls[0]["reply"] == response.reply
    assert persistence.calls[0]["safety_flag"] == "ok"


@pytest.mark.asyncio
async def test_handle_chat_demo_persists_safety_fallback():
    """Safety 拦截仍应保存用户输入和 fallback，但不调用 LLM。"""
    persistence = _FakePersistence()
    response = await handle_chat_demo(
        ChatDemoRequest(
            user_text="我想自杀",
            external_user_id="browser-user-1",
            scene=Scene.LONELINESS,
        ),
        safety_provider=LocalOnlySafetyProvider(),
        provider=_FakeFailingProvider(),
        classifier=_SpyClassifier(),
        is_mock=False,
        persistence=persistence,
    )

    assert response.conversation_id == persistence.conversation_id
    assert len(persistence.calls) == 1
    assert persistence.calls[0]["safety_flag"] == "crisis_keyword"
    assert persistence.calls[0]["reply"] == response.reply


# [2026-07-29] 以下用例覆盖新加的 history 服务端字符预算（_build_history）。
def test_build_history_returns_none_for_empty() -> None:
    """空 history 应返回 None，保持原有「不传 history 字段」的行为。"""
    assert _build_history([]) is None


def test_build_history_passes_through_normal_conversation() -> None:
    """真实会话远低于预算，必须原样透传、顺序不变。"""
    messages = [
        HistoryMessage(role="user" if i % 2 == 0 else "assistant", content=f"第{i}句")
        for i in range(20)
    ]

    result = _build_history(messages)

    assert result is not None
    assert len(result) == 20
    assert result[0]["content"] == "第0句"
    assert result[-1]["content"] == "第19句"


def test_build_history_truncates_to_char_budget_keeping_newest() -> None:
    """超预算时丢最早的、保住最近的上下文，且总字符数不超过预算。"""
    # 100 条 × 2000 字符 = 20 万字符：条数在 schemas 的 200 条上限之内，
    # 但体积远超预算——正是字符预算这一层要挡的情况。
    messages = [
        HistoryMessage(role="user", content=f"{i:04d}" + "x" * 1996) for i in range(100)
    ]

    result = _build_history(messages)

    assert result is not None
    assert len(result) < 100
    assert sum(len(m["content"]) for m in result) <= _MAX_HISTORY_CHARS
    # 保留的是尾部，所以最后一条仍是原始输入的最后一条。
    assert result[-1]["content"].startswith("0099")
