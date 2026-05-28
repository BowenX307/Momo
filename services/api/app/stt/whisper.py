"""Whisper 兼容 STT provider。

封装 OpenAI `/v1/audio/transcriptions` 协议；`whisper_base_url` 可指向 OpenAI
或任意兼容端点（如 SiliconFlow 等代理），便于国内接入。
"""

import httpx

from app.core.config import settings
from app.stt.provider import STTError, TranscriptionResult


def _guess_filename(content_type: str | None, filename: str | None) -> str:
    if filename:
        return filename
    if content_type and "webm" in content_type:
        return "audio.webm"
    if content_type and "mp4" in content_type:
        return "audio.m4a"
    if content_type and "wav" in content_type:
        return "audio.wav"
    if content_type and "mpeg" in content_type:
        return "audio.mp3"
    return "audio.webm"


class WhisperSTTProvider:
    """Whisper API 转写。任何失败统一抛 `STTError`。"""

    async def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> TranscriptionResult:
        name = _guess_filename(content_type, filename)
        mime = content_type or "application/octet-stream"
        files = {"file": (name, audio, mime)}
        data = {
            "model": settings.whisper_model,
            "language": "zh",
            "response_format": "json",
        }
        headers = {"Authorization": f"Bearer {settings.whisper_api_key}"}
        url = f"{settings.whisper_base_url.rstrip('/')}/audio/transcriptions"

        try:
            async with httpx.AsyncClient(
                timeout=settings.stt_timeout_seconds
            ) as client:
                response = await client.post(
                    url, headers=headers, files=files, data=data
                )
        except httpx.TimeoutException as exc:
            raise STTError("timeout", f"whisper timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise STTError("network", f"whisper network error: {exc}") from exc

        if response.status_code != 200:
            raise STTError(
                "http_status",
                f"whisper non-200: {response.status_code}",
                upstream_status=response.status_code,
            )

        try:
            payload = response.json()
            text = str(payload["text"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise STTError("decode", f"whisper decode error: {exc}") from exc

        return TranscriptionResult(text=text)
