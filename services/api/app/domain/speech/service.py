"""语音转写编排。"""

import base64
import re
from uuid import uuid4

import structlog

from app.domain.speech.schemas import (
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeResponse,
)
from app.stt.provider import STTError, STTProvider
from app.tts.provider import TTSError, TTSProvider

logger = structlog.get_logger(__name__)

# 单段录音上限（约 60s webm/opus 量级），防止超大上传拖垮服务
_MAX_AUDIO_BYTES = 10 * 1024 * 1024

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"\*(.+?)\*")
_BRACKETS = re.compile(r"[【】《》〔〕\[\]「」『』]")
_EM_DASH = re.compile(r"——+")
_LIST_MARKER = re.compile(r"^\s*[\d一二三四五六七八九十]+[.、.]\s*", re.MULTILINE)
_MULTI_SPACE = re.compile(r"  +")


_SENTENCE_END = frozenset("。？！…")


def _clean_for_tts(text: str) -> str:
    """去除 markdown 和排版符号，确保末尾有句号（防止 TTS 截断最后几个字）。"""
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _BRACKETS.sub("", text)
    text = _EM_DASH.sub("，", text)
    text = _LIST_MARKER.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = text.strip()
    if text and text[-1] not in _SENTENCE_END:
        text += "。"
    return text


async def handle_transcribe(
    audio: bytes,
    *,
    content_type: str | None,
    filename: str | None,
    provider: STTProvider,
    is_mock: bool,
) -> TranscribeResponse:
    """处理一次语音转写请求。"""
    request_id = uuid4().hex

    if not audio:
        logger.info("transcribe_empty_audio", request_id=request_id)
        return TranscribeResponse(
            text="",
            is_mock=is_mock,
            request_id=request_id,
        )

    if len(audio) > _MAX_AUDIO_BYTES:
        logger.warning(
            "transcribe_audio_too_large",
            request_id=request_id,
            size_bytes=len(audio),
        )
        raise ValueError("audio_too_large")

    try:
        result = await provider.transcribe(
            audio,
            content_type=content_type,
            filename=filename,
        )
        logger.info(
            "transcribe_ok",
            request_id=request_id,
            is_mock=is_mock,
            text_chars=len(result.text),
        )
        return TranscribeResponse(
            text=result.text,
            language=result.language,
            is_mock=is_mock,
            request_id=request_id,
        )
    except STTError as exc:
        logger.warning(
            "transcribe_stt_failed",
            request_id=request_id,
            error_code=exc.code,
            upstream_status=exc.upstream_status,
        )
        raise


async def handle_synthesize(
    request: SynthesizeRequest,
    provider: TTSProvider,
    is_mock: bool,
) -> SynthesizeResponse:
    """处理一次语音合成请求。"""
    request_id = uuid4().hex

    try:
        clean_text = _clean_for_tts(request.text)
        result = await provider.synthesize(clean_text)
        audio_b64 = (
            base64.b64encode(result.audio).decode("ascii") if result.audio else ""
        )
        logger.info(
            "synthesize_ok",
            request_id=request_id,
            is_mock=is_mock,
            text_chars=len(request.text),
            audio_bytes=len(result.audio),
        )
        return SynthesizeResponse(
            audio_base64=audio_b64,
            content_type=result.content_type,
            is_mock=is_mock,
            request_id=request_id,
        )
    except TTSError as exc:
        logger.warning(
            "synthesize_tts_failed",
            request_id=request_id,
            error_code=exc.code,
            error_message=str(exc),
            upstream_status=exc.upstream_status,
        )
        raise
