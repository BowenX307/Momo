"""MiniMax 同步语音合成（T2A v2）。

文档：https://platform.minimaxi.com/docs/api-reference/speech-t2a-http
"""

import httpx

from app.core.config import settings
from app.tts.provider import SynthesisResult, TTSError

# 按 scene 微调语速，贴合 MOMO「慢慢说、不抢话」的人设
_SCENE_SPEED: dict[str, float] = {
    "late_night": 0.88,
    "rumination": 0.9,
    "relationship": 0.92,
    "stress": 0.9,
    "loneliness": 0.9,
}


def _speed_for(scene: str | None) -> float:
    if scene and scene in _SCENE_SPEED:
        return _SCENE_SPEED[scene]
    return settings.minimax_tts_speed


class MiniMaxTTSProvider:
    """MiniMax T2A v2。失败统一抛 `TTSError`。"""

    async def synthesize(
        self,
        text: str,
        *,
        scene: str | None = None,
    ) -> SynthesisResult:
        stripped = text.strip()
        if not stripped:
            return SynthesisResult(audio=b"")

        payload = {
            "model": settings.minimax_tts_model,
            "text": stripped,
            "stream": False,
            "voice_setting": {
                "voice_id": settings.minimax_tts_voice_id,
                "speed": _speed_for(scene),
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
            "language_boost": "Chinese",
        }
        headers = {
            "Authorization": f"Bearer {settings.minimax_api_key}",
            "Content-Type": "application/json",
        }
        url = (
            f"{settings.minimax_base_url.rstrip('/')}/v1/t2a_v2"
            f"?GroupId={settings.minimax_group_id}"
        )

        try:
            async with httpx.AsyncClient(
                timeout=settings.tts_timeout_seconds
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise TTSError("timeout", f"minimax tts timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TTSError("network", f"minimax tts network error: {exc}") from exc

        if response.status_code != 200:
            raise TTSError(
                "http_status",
                f"minimax tts non-200: {response.status_code}",
                upstream_status=response.status_code,
            )

        try:
            data = response.json()
            base = data.get("base_resp") or {}
            if base.get("status_code", -1) != 0:
                code = base.get("status_code")
                msg = base.get("status_msg", "unknown")
                raise TTSError(
                    "upstream",
                    f"minimax tts error ({code}): {msg}",
                )
            audio_hex = data["data"]["audio"]
            audio = bytes.fromhex(audio_hex)
        except TTSError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise TTSError("decode", f"minimax tts decode error: {exc}") from exc

        if not audio:
            raise TTSError("empty_audio", "minimax tts returned empty audio")

        return SynthesisResult(audio=audio, content_type="audio/mpeg")
