"""SiliconFlow TTS（CosyVoice2，OpenAI 兼容接口）。

复用 WHISPER_API_KEY / WHISPER_BASE_URL，不需要额外注册账号。
"""

import httpx

from app.core.config import settings
from app.tts.provider import SynthesisResult, TTSError



class SiliconFlowTTSProvider:
    """SiliconFlow CosyVoice2 TTS。失败统一抛 TTSError。"""

    async def synthesize(
        self,
        text: str,
    ) -> SynthesisResult:
        stripped = text.strip()
        if not stripped:
            return SynthesisResult(audio=b"")

        payload = {
            "model": settings.siliconflow_tts_model,
            "input": stripped,
            "voice": settings.siliconflow_tts_voice,
            "response_format": "mp3",
            "speed": settings.siliconflow_tts_speed,
        }
        headers = {
            "Authorization": f"Bearer {settings.whisper_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.whisper_base_url.rstrip('/')}/audio/speech"

        try:
            async with httpx.AsyncClient(
                timeout=settings.tts_timeout_seconds
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise TTSError("timeout", f"siliconflow tts timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TTSError("network", f"siliconflow tts network error: {exc}") from exc

        if response.status_code != 200:
            raise TTSError(
                "http_status",
                f"siliconflow tts non-200: {response.status_code} {response.text[:200]}",
                upstream_status=response.status_code,
            )

        audio = response.content
        if not audio:
            raise TTSError("empty_audio", "siliconflow tts returned empty audio")

        return SynthesisResult(audio=audio, content_type="audio/mpeg")
