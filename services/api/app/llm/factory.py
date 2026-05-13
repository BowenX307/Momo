"""按运行时配置选 LLM provider。

返回 `(provider, is_mock)`：`is_mock` 透给上层供日志与响应字段使用，
方便前端在 demo 阶段直观看到「这条回复是不是 mock」。
"""

from app.core.config import settings
from app.llm.deepseek import DeepSeekProvider
from app.llm.provider import LLMProvider, MockProvider


def get_llm_provider() -> tuple[LLMProvider, bool]:
    if settings.llm_provider == "deepseek" and settings.deepseek_api_key:
        return DeepSeekProvider(), False
    return MockProvider(), True
