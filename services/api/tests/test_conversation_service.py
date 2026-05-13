"""会话编排单元测试。用假 provider 覆盖各分支，不打真实网络。"""

import pytest

from app.domain.conversation.schemas import ChatDemoRequest, Scene
from app.domain.conversation.service import handle_chat_demo
from app.llm.provider import LLMError, LLMProvider


class _FakeOkProvider:
    async def complete(self, scene: str, user_text: str) -> str:  # noqa: D401
        return f"fake-reply for {scene}: {user_text}"


class _FakeFailingProvider:
    def __init__(self, code: str = "http_status", status: int | None = 402) -> None:
        self.code = code
        self.status = status

    async def complete(self, scene: str, user_text: str) -> str:
        raise LLMError(self.code, "boom", upstream_status=self.status)


@pytest.mark.asyncio
async def test_handle_chat_demo_returns_provider_reply_on_success():
    provider: LLMProvider = _FakeOkProvider()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="今晚胸口闷", scene=Scene.LATE_NIGHT),
        provider=provider,
        is_mock=False,
    )
    assert response.reply.startswith("fake-reply for late_night")
    assert response.safety_flag == "ok"
    assert response.is_mock is False
    assert response.degraded is False


@pytest.mark.asyncio
async def test_handle_chat_demo_degrades_to_mock_on_llm_error():
    """真 provider 抛 LLMError 时应降级到 MockProvider，并把 degraded=True 透传。"""
    provider: LLMProvider = _FakeFailingProvider(code="http_status", status=402)
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="今晚胸口闷", scene=Scene.LATE_NIGHT),
        provider=provider,
        is_mock=False,
    )
    assert response.degraded is True
    assert response.is_mock is True
    assert response.safety_flag == "ok"
    assert response.reply  # MockProvider 必须给出可渲染回复


@pytest.mark.asyncio
async def test_handle_chat_demo_safety_blocks_before_llm():
    """危机关键词应直接走固定文案，不调用 provider（即使 provider 会抛错也不会被触发）。"""
    provider: LLMProvider = _FakeFailingProvider()
    response = await handle_chat_demo(
        ChatDemoRequest(user_text="我想自杀", scene=Scene.LATE_NIGHT),
        provider=provider,
        is_mock=False,
    )
    assert response.safety_flag == "crisis_keyword"
    assert response.degraded is False  # safety 路径不算降级
    assert "诊断" not in response.reply
    assert "治疗" not in response.reply
