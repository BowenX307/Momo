"""豆包语音合成模型（火山引擎 V3 HTTP Chunked）。

响应格式：换行分隔的 JSON 流，每行 {"code":0,"message":"","data":"<base64_mp3_chunk>"}
"""

import base64
import json
import re

import httpx

from app.core.config import settings
from app.tts.provider import SynthesisResult, TTSError

_ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
_RESOURCE_ID = "seed-tts-2.0"

_DEFAULT_RATE = -8  # range [-50, 100]

_MIN_CLAUSE_LEN = 8  # 逗号两侧从句都要达到此长度才插停顿
_MIN_TEXT_LEN = 20  # 短文本不处理


def _with_natural_pauses(text: str) -> str:
    """在长从句的逗号后插入 SSML break，只在两侧从句都够长时才停顿。"""
    if len(text) < _MIN_TEXT_LEN:
        return text
    parts = re.split(r"([，,])", text)
    out: list[str] = []
    last_clause_len = 0
    for chunk in parts:
        if chunk in ("，", ","):
            out.append(chunk)
        else:
            clause_len = len(chunk.strip())
            if (
                out
                and out[-1] in ("，", ",")
                and last_clause_len >= _MIN_CLAUSE_LEN
                and clause_len >= _MIN_CLAUSE_LEN
            ):
                out.append('<break time="300ms"/>')
            out.append(chunk)
            last_clause_len = clause_len
    return f"<speak>{''.join(out)}</speak>"


class DoubaoTTSProvider:
    """豆包 V3 TTS（seed-tts-2.0）。失败统一抛 TTSError。"""

    async def synthesize(
        self,
        text: str,
        *,
        scene: str | None = None,
    ) -> SynthesisResult:
        stripped = text.strip()
        if not stripped:
            return SynthesisResult(audio=b"")

        speech_rate = _DEFAULT_RATE

        payload = {
            "user": {"uid": "momo"},
            "req_params": {
                "text": _with_natural_pauses(stripped),
                "speaker": settings.doubao_tts_voice,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": speech_rate,
                },
                "additions": json.dumps(
                    {
                        "post_process": {"pitch": settings.doubao_tts_pitch},
                        "disable_markdown_filter": True,
                        "enable_ssml": True,
                    }
                ),
            },
        }
        headers = {
            "X-Api-Key": settings.doubao_tts_api_key,
            "X-Api-Resource-Id": _RESOURCE_ID,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.tts_timeout_seconds
            ) as client:
                response = await client.post(_ENDPOINT, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise TTSError("timeout", f"doubao tts timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TTSError("network", f"doubao tts network error: {exc}") from exc

        if response.status_code != 200:
            raise TTSError(
                "http_status",
                f"doubao tts {response.status_code}: {response.text[:300]}",
                upstream_status=response.status_code,
            )

        # 响应是换行分隔的 JSON 流，每行 {"code":0,"data":"<base64>"}
        chunks: list[bytes] = []
        for line in response.content.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = obj.get("code", 0)
            if code not in (0, 20000000) and obj.get("data") is None:
                raise TTSError(
                    "api_error",
                    f"doubao tts error: {obj.get('message', '')} (code {code})",
                )
            if obj.get("data"):
                chunks.append(base64.b64decode(obj["data"]))

        if not chunks:
            raise TTSError("empty_audio", "doubao tts returned no audio chunks")

        return SynthesisResult(audio=b"".join(chunks), content_type="audio/mpeg")
