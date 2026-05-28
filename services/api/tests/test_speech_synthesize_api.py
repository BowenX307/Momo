"""POST /v1/speech/synthesize 端到端冒烟测试。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _force_mock_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tts_provider", "mock")


def test_synthesize_returns_mock_empty_audio():
    resp = client.post(
        "/v1/speech/synthesize",
        json={"text": "我在的，慢慢说。", "scene": "loneliness"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["audio_base64"] == ""
    assert body["content_type"] == "audio/mpeg"
    assert body["is_mock"] is True
    assert body["request_id"]


def test_synthesize_rejects_empty_text():
    resp = client.post("/v1/speech/synthesize", json={"text": ""})
    assert resp.status_code == 422
