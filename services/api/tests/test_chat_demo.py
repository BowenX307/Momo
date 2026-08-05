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
    assert "scene" not in body, "scene 已随场景分类移除，不应再出现在响应里"
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


def test_chat_demo_tolerates_legacy_scene_field():
    """[2026-08-03] 场景分类已移除，但线上老客户端(尤其 Unity)仍会回传 scene。

    收下即丢弃，绝不能 422——那会让还没更新的 Unity 客户端整个挂掉。
    任意取值都要放行，包括原先合法的和从来没有过的。
    """
    for value in ("late_night", "not_a_real_scene", "", None):
        resp = client.post(
            "/v1/chat/demo",
            json={"user_text": "hi", "scene": value},
        )
        assert resp.status_code == 200, f"scene={value!r} 应被容忍: {resp.text}"
        assert "scene" not in resp.json()


def test_chat_demo_skips_persistence_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """即使请求带匿名用户 ID，配置关闭时也不创建数据库会话。"""
    monkeypatch.setattr(settings, "persistence_enabled", False)

    resp = client.post(
        "/v1/chat/demo",
        json={
            "user_text": "今天有点累",
            "external_user_id": "browser-test-user",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["conversation_id"] is None


def test_guest_chat_never_persists_even_with_external_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开启数据库后，未登录游客仍然只在浏览器保存。"""
    monkeypatch.setattr(settings, "persistence_enabled", True)

    resp = client.post(
        "/v1/chat/demo",
        json={
            "user_text": "游客也可以聊",
            "scene": "loneliness",
            "external_user_id": "browser-test-user",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["conversation_id"] is None
