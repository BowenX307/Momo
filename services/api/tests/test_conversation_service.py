"""会话编排单元测试。用假 provider / 假 classifier 覆盖各分支，不打真实网络。"""

import pytest

from app.domain.conversation.schemas import ChatDemoRequest, Scene
from app.domain.conversation.service import handle_chat_demo
from app.llm.classifier import SceneClassifier
from app.llm.provider import LLMError, LLMProvider


class _FakeOkProvider:
    async def complete(
        self, scene: str, user_text: str, history: list[dict] | None = None
    ) -> str:
        return f"fake-reply for {scene}: {user_text}"


class _FakeFailingProvider:
    def __init__(self, code: str = "http_status", status: int | None = 402) -> None:
        self.code = code
        self.status = status

    async def complete(
        self, scene: str, user_text: str, history: list[dict] | None = None
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


@pytest.mark.asyncio
async def test_handle_chat_demo_uses_explicit_scene_and_skips_classifier():
    """前端传了 scene → service 必须直接用，不调用 classifier。"""
    provider: LLMProvider = _FakeOkProvider()
    classifier = _SpyClassifier()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="今晚胸口闷", scene=Scene.LATE_NIGHT),
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
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="他根本就不在乎我", scene=None),
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
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="今晚胸口闷", scene=Scene.LATE_NIGHT),
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
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="我想自杀", scene=None),
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
