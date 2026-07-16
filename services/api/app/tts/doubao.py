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

# 按人格覆盖 音色 / 资源版本 / 语速。未列出的人格用全局 settings.doubao_tts_voice
# + 默认 _RESOURCE_ID + _DEFAULT_RATE。
# youyou（优优）= 高洞察力·有点毒嘴的老朋友 → 京腔侃爷（嘴碎调侃感，seed-tts-1.0，
#         2026-07-16 试音选定，替换原少年梓辛）。参数与试音样本一致:语速 -6、不动音调。
_PERSONA_VOICE_OVERRIDES: dict[str, dict[str, object]] = {
    "youyou": {
        "speaker": "zh_male_jingqiangkanye_moon_bigtts",
        "resource_id": "seed-tts-1.0",
        "speech_rate": -6,
        "pitch": 0.0,  # 全局 -2 降调不适用,保持原声(试音样本就是原声)
    },
}

_MIN_CLAUSE_LEN = 8   # 逗号两侧从句都要达到此长度才插停顿
_MIN_TEXT_LEN = 20    # 短文本不处理


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
    return f'<speak>{"".join(out)}</speak>'


class DoubaoTTSProvider:
    """豆包 V3 TTS（seed-tts-2.0）。失败统一抛 TTSError。"""

    async def synthesize(
        self,
        text: str,
        *,
        scene: str | None = None,
        persona: str | None = None,
    ) -> SynthesisResult:
        stripped = text.strip()
        if not stripped:
            return SynthesisResult(audio=b"")

        override = _PERSONA_VOICE_OVERRIDES.get(persona or "", {})
        voice = str(override.get("speaker", settings.doubao_tts_voice))
        resource_id = str(override.get("resource_id", _RESOURCE_ID))
        speech_rate = int(override.get("speech_rate", _DEFAULT_RATE))
        pitch = float(override.get("pitch", settings.doubao_tts_pitch))

        payload = {
            "user": {"uid": "yewne"},
            "req_params": {
                "text": _with_natural_pauses(stripped),
                "speaker": voice,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": speech_rate,
                },
                "additions": json.dumps({
                    "post_process": {"pitch": pitch},
                    "disable_markdown_filter": True,
                    "enable_ssml": True,
                }),
            },
        }
        headers = {
            "X-Api-Key": settings.doubao_tts_api_key,
            "X-Api-Resource-Id": resource_id,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.tts_timeout_seconds) as client:
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
