"""POST /v1/speech/transcribe 端到端冒烟测试。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _force_mock_stt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stt_provider", "mock")


def test_transcribe_returns_mock_text():
    resp = client.post(
        "/v1/speech/transcribe",
        files={"audio": ("clip.webm", b"x" * 500, "audio/webm")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["text"]
    assert body["language"] == "zh"
    assert body["is_mock"] is True
    assert body["request_id"]


def test_transcribe_empty_file_returns_empty_text():
    resp = client.post(
        "/v1/speech/transcribe",
        files={"audio": ("empty.webm", b"", "audio/webm")},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == ""


def test_transcribe_rejects_unsupported_content_type():
    resp = client.post(
        "/v1/speech/transcribe",
        files={"audio": ("doc.pdf", b"%PDF", "application/pdf")},
    )
    assert resp.status_code == 415
