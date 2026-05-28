"""按运行时配置选 STT provider。"""

from app.core.config import settings
from app.stt.provider import MockSTTProvider, STTProvider
from app.stt.whisper import WhisperSTTProvider


def _use_real_stt() -> bool:
    return settings.stt_provider == "whisper" and bool(settings.whisper_api_key)


def get_stt_provider() -> tuple[STTProvider, bool]:
    if _use_real_stt():
        return WhisperSTTProvider(), False
    return MockSTTProvider(), True
