"""POST /v1/chat/demo 端到端冒烟测试。

强制走 MockProvider，避免依赖 .env 实际配置 / 真实网络。
真 provider 的行为由 `tests/test_deepseek_provider.py` 与
`tests/test_conversation_service.py` 覆盖。
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "mock")


client = TestClient(app)


def test_chat_demo_returns_mock_reply():
    resp = client.post(
        "/v1/chat/demo",
        json={"user_text": "今晚睡不着，脑子里全是工作", "scene": "late_night"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reply"]
    assert body["scene"] == "late_night"
    assert body["safety_flag"] == "ok"
    assert body["is_mock"] is True
    assert body["request_id"]


def test_chat_demo_safety_fallback_on_crisis_keyword():
    resp = client.post(
        "/v1/chat/demo",
        json={"user_text": "我活不下去了", "scene": "late_night"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["safety_flag"] == "crisis_keyword"
    # 降级文案应包含连接现实支持的内容，且不含医疗化措辞
    assert "诊断" not in body["reply"]
    assert "治疗" not in body["reply"]


def test_chat_demo_empty_input_falls_back():
    resp = client.post(
        "/v1/chat/demo",
        json={"user_text": "   ", "scene": "loneliness"},
    )
    assert resp.status_code == 200
    assert resp.json()["safety_flag"] == "empty_input"


def test_chat_demo_rejects_unknown_scene():
    resp = client.post(
        "/v1/chat/demo",
        json={"user_text": "hi", "scene": "not_a_real_scene"},
    )
    assert resp.status_code == 422
