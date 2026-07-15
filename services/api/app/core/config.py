"""应用配置 - 通过环境变量加载"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    """全局配置。所有敏感配置通过 .env 文件加载。"""

    # 环境
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True

    # CORS
    cors_origins: list[str] = ["*"]  # 生产环境必须收紧

    # 数据库（暂未启用）
    database_url: str = "postgresql+psycopg://momo:momo@localhost:5432/momo"

    # Redis（暂未启用）
    redis_url: str = "redis://localhost:6379/0"

    # LLM 供应商选择：dev 默认走 mock；要接真模型时设为 "deepseek" 并填 key
    llm_provider: Literal["mock", "deepseek"] = "mock"
    llm_timeout_seconds: float = 30.0

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # 豆包（LLM 备用，暂未接入）
    doubao_api_key: str = ""

    # STT（语音转文字）
    # 默认 mock，离线/无 key 也能跑 demo；要接真模型改成 "whisper" 并填 WHISPER_API_KEY
    stt_provider: Literal["mock", "whisper"] = "mock"
    stt_timeout_seconds: float = 30.0
    whisper_api_key: str = ""
    whisper_base_url: str = "https://api.siliconflow.cn/v1"
    whisper_model: str = "FunAudioLLM/SenseVoiceSmall"

    # TTS（文字转语音）
    tts_provider: Literal["mock", "minimax", "siliconflow", "doubao"] = "mock"
    tts_timeout_seconds: float = 60.0

    # MiniMax TTS
    minimax_api_key: str = ""
    minimax_group_id: str = ""
    minimax_base_url: str = "https://api.minimaxi.com"
    minimax_tts_model: str = "speech-2.8-turbo"
    minimax_tts_voice_id: str = "female-tianmei"
    minimax_tts_speed: float = 0.92

    # SiliconFlow TTS（复用 WHISPER_API_KEY / WHISPER_BASE_URL）
    siliconflow_tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    siliconflow_tts_voice: str = "FunAudioLLM/CosyVoice2-0.5B:anna"
    siliconflow_tts_speed: float = 0.92

    # 豆包 TTS（火山引擎 V3，seed-tts-2.0）
    doubao_tts_api_key: str = ""
    doubao_tts_voice: str = "zh_female_xiaohe_uranus_bigtts"
    doubao_tts_pitch: float = -2.0  # [-12, 12]，负值降调

    # 内容安全
    safety_provider: Literal["mock", "aliyun"] = "mock"
    safety_timeout_seconds: float = 10.0
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_safety_base_url: str = "https://green-cip.cn-hangzhou.aliyuncs.com"
    aliyun_safety_api_version: str = "2022-03-02"
    aliyun_safety_service: str = "ugc_moderation_byllm_pro"
    aliyun_region_id: str = "cn-hangzhou"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
