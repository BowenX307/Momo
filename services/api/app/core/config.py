"""应用配置 - 通过环境变量加载"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    """全局配置。所有敏感配置通过 .env 文件加载。"""

    # 环境
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True

    # CORS —— 允许跨源访问本 API 的站点白名单。
    # [2026-07-29] 原值是 ["*"](任何站点),配合 allow_credentials=True 时 Starlette 会
    # 回显调用方 Origin 并附带 Allow-Credentials,等于给每个源都发了一张带凭证的通行证。
    #
    # 线上 uniai.net.cn 同时提供前端页面和 /v1 API,属于同源,浏览器不做 CORS 检查,
    # 所以收紧这里对线上网页没有影响;Unity 与手机 App 是原生客户端,也不受 CORS 约束。
    # 真正需要放行的只有本地开发(localhost:3000 → 127.0.0.1:8000 端口不同即跨域)。
    #
    # 要新增域名(预览环境 / 测试环境 / 其它子域)时:改 .env 里的 CORS_ORIGINS,逗号分隔,
    # 不要改这里的默认值——默认值只作为没配 .env 时的兜底。带协议头,不要写路径,例如:
    #   CORS_ORIGINS=https://uniai.net.cn,https://staging.uniai.net.cn
    cors_origins: list[str] = [
        "https://uniai.net.cn",
        "https://www.uniai.net.cn",  # 带 www 在浏览器眼里是另一个源
        "http://localhost:3000",
        "http://127.0.0.1:3000",  # 与 localhost 同样视为不同源,两个都要写
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated_origins(cls, v: object) -> object:
        """允许 .env 里写 `a,b,c` 而不是 JSON 数组，配置起来更顺手。"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # 数据库持久化；默认关闭，未安装 PostgreSQL 也能运行聊天功能
    persistence_enabled: bool = False
    database_url: str = (
        "postgresql+psycopg://yewne:yewne_dev_password@localhost:5432/yewne_dev"
    )
    database_health_timeout_seconds: float = 2.0

    # Redis（验证码 + 登录 token 存这里）
    redis_url: str = "redis://localhost:6379/0"

    # LLM 供应商选择：dev 默认走 mock；要接真模型时设为 "deepseek" 并填 key
    llm_provider: Literal["mock", "deepseek"] = "mock"
    llm_timeout_seconds: float = 30.0

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"

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

    # 短信验证码登录
    # ⚠️ 专用独立的 key,不能复用上面内容安全的 aliyun_access_key_id/secret——
    # 那把是 Ronnie 的账号，没有 dysms 权限；这把短信 key 也没有内容安全权限，
    # 两个用途混用一把 key 会导致其中一个功能静默失效(2026-07-28 踩过账号不对的坑)。
    sms_provider: Literal["mock", "aliyun"] = "mock"
    sms_timeout_seconds: float = 10.0
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = ""
    aliyun_sms_template_code: str = ""
    aliyun_sms_region_id: str = "cn-hangzhou"
    sms_code_ttl_seconds: int = 300  # 验证码有效期 5 分钟
    sms_resend_cooldown_seconds: int = 60  # 同一手机号防连点
    sms_daily_limit: int = 10  # 单手机号每日最多发送次数

    # 登录态 token(服务端存储的随机字符串,不是 JWT,方便主动撤销)
    auth_token_ttl_days: int = 30

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
