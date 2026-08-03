"""POST /v1/speech/transcribe —— 语音转文字入口。

接收 multipart 音频文件，返回转写文本。后续 chat 链路仍走 /v1/chat/demo，
本接口只负责「听」。
"""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.api.v1.deps import RedisDep, enforce_rate_limit
from app.core.config import settings
from app.domain.speech.schemas import (
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeResponse,
)
from app.domain.speech.service import handle_synthesize, handle_transcribe
from app.stt.factory import get_stt_provider
from app.stt.provider import STTError
from app.tts.factory import get_tts_provider
from app.tts.provider import TTSError

router = APIRouter(prefix="/speech", tags=["speech"])

_ALLOWED_CONTENT_PREFIXES = ("audio/", "video/webm", "application/octet-stream")


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    http_request: Request,
    redis: RedisDep,
    audio: UploadFile = File(...),
) -> TranscribeResponse:
    # 这两个语音接口请求里没有任何身份标识(只有音频/文本),所以只能按 IP 限。
    # 见 deps.client_ip 的说明：nginx 未确认是否转发真实 IP。
    await enforce_rate_limit(
        http_request,
        redis,
        bucket="speech",
        limit=settings.rate_limit_speech_per_minute,
        identity=None,
    )
    content_type = audio.content_type
    if content_type and not any(
        content_type.startswith(p) if p.endswith("/") else content_type == p
        for p in _ALLOWED_CONTENT_PREFIXES
    ):
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content type: {content_type}",
        )

    raw = await audio.read()
    provider, is_mock = get_stt_provider()

    try:
        return await handle_transcribe(
            raw,
            content_type=content_type,
            filename=audio.filename,
            provider=provider,
            is_mock=is_mock,
        )
    except ValueError as exc:
        if str(exc) == "audio_too_large":
            raise HTTPException(status_code=413, detail="audio file too large") from exc
        raise
    except STTError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    request: SynthesizeRequest,
    http_request: Request,
    redis: RedisDep,
) -> SynthesizeResponse:
    await enforce_rate_limit(
        http_request,
        redis,
        bucket="speech",
        limit=settings.rate_limit_speech_per_minute,
        identity=None,
    )
    provider, is_mock = get_tts_provider()
    try:
        return await handle_synthesize(request, provider=provider, is_mock=is_mock)
    except TTSError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
