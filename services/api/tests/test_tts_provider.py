"""TTS provider 单元测试。"""

import httpx
import pytest
import respx

from app.core.config import settings
from app.tts.minimax import MiniMaxTTSProvider
from app.tts.provider import MockTTSProvider, TTSError


@pytest.mark.asyncio
async def test_mock_tts_returns_empty_audio():
    result = await MockTTSProvider().synthesize("你好")
    assert result.audio == b""
    assert result.content_type == "audio/mpeg"


@pytest.mark.asyncio
async def test_minimax_synthesize_returns_mp3_on_success():
    provider = MiniMaxTTSProvider()
    url = (
        f"{settings.minimax_base_url.rstrip('/')}/v1/t2a_v2"
        f"?GroupId={settings.minimax_group_id}"
    )
    fake_mp3 = b"\xff\xfb"
    with respx.mock(assert_all_called=True) as mock:
        mock.post(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"audio": fake_mp3.hex(), "status": 2},
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                },
            )
        )
        result = await provider.synthesize("我在的。", scene="late_night")
    assert result.audio == fake_mp3


@pytest.mark.asyncio
async def test_minimax_synthesize_raises_on_upstream_error():
    provider = MiniMaxTTSProvider()
    url = (
        f"{settings.minimax_base_url.rstrip('/')}/v1/t2a_v2"
        f"?GroupId={settings.minimax_group_id}"
    )
    with respx.mock() as mock:
        mock.post(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"audio": "", "status": 2},
                    "base_resp": {
                        "status_code": 1008,
                        "status_msg": "insufficient balance",
                    },
                },
            )
        )
        with pytest.raises(TTSError) as exc_info:
            await provider.synthesize("你好")
        assert exc_info.value.code == "upstream"
