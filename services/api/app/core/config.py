"""应用配置 - 通过环境变量加载"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # 豆包（备份 provider，暂未接入）
    doubao_api_key: str = ""

    # 内容安全（暂未启用）
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
