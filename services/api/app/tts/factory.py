"""按运行时配置选 TTS provider。"""

from app.core.config import settings
from app.tts.doubao import DoubaoTTSProvider
from app.tts.minimax import MiniMaxTTSProvider
from app.tts.provider import MockTTSProvider, TTSProvider
from app.tts.siliconflow import SiliconFlowTTSProvider


def get_tts_provider() -> tuple[TTSProvider, bool]:
    if settings.tts_provider == "doubao" and settings.doubao_tts_api_key:
        return DoubaoTTSProvider(), False
    if (
        settings.tts_provider == "minimax"
        and settings.minimax_api_key
        and settings.minimax_group_id
    ):
        return MiniMaxTTSProvider(), False
    if settings.tts_provider == "siliconflow" and settings.whisper_api_key:
        return SiliconFlowTTSProvider(), False
    return MockTTSProvider(), True
