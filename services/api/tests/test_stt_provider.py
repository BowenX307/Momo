"""STT provider 单元测试。"""

import httpx
import pytest
import respx

from app.core.config import settings
from app.stt.provider import MockSTTProvider, STTError
from app.stt.whisper import WhisperSTTProvider


@pytest.mark.asyncio
async def test_mock_stt_returns_empty_for_tiny_audio():
    result = await MockSTTProvider().transcribe(b"")
    assert result.text == ""


@pytest.mark.asyncio
async def test_mock_stt_returns_sample_for_realistic_audio():
    audio = b"x" * 500
    result = await MockSTTProvider().transcribe(audio)
    assert result.text
    assert result.language == "zh"


@pytest.mark.asyncio
async def test_whisper_transcribe_returns_text_on_200():
    provider = WhisperSTTProvider()
    url = f"{settings.whisper_base_url.rstrip('/')}/audio/transcriptions"
    with respx.mock(assert_all_called=True) as mock:
        mock.post(url).mock(
            return_value=httpx.Response(200, json={"text": "  今晚睡不着  "})
        )
        result = await provider.transcribe(
            b"fake-audio-bytes",
            content_type="audio/webm",
            filename="clip.webm",
        )
    assert result.text == "今晚睡不着"


@pytest.mark.asyncio
async def test_whisper_transcribe_raises_on_non_200():
    provider = WhisperSTTProvider()
    url = f"{settings.whisper_base_url.rstrip('/')}/audio/transcriptions"
    with respx.mock() as mock:
        mock.post(url).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
        with pytest.raises(STTError) as exc_info:
            await provider.transcribe(b"audio")
        assert exc_info.value.code == "http_status"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_whisper_transcribe_raises_on_timeout():
    provider = WhisperSTTProvider()
    url = f"{settings.whisper_base_url.rstrip('/')}/audio/transcriptions"
    with respx.mock() as mock:
        mock.post(url).mock(side_effect=httpx.TimeoutException("slow"))
        with pytest.raises(STTError) as exc_info:
            await provider.transcribe(b"audio")
        assert exc_info.value.code == "timeout"
