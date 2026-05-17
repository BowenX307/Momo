"""按运行时配置选 LLM provider 与 scene classifier。

`get_llm_provider()` 返回 `(provider, is_mock)`：`is_mock` 透给上层供日志与响应字段
使用，方便前端在 demo 阶段直观看到「这条回复是不是 mock」。

`get_scene_classifier()` 返回独立的分类器实现：与对话 provider 同构，配置为
deepseek 且有 key 时走 DeepSeek，否则走 MockClassifier。
"""

from app.core.config import settings
from app.llm.classifier import DeepSeekClassifier, MockClassifier, SceneClassifier
from app.llm.deepseek import DeepSeekProvider
from app.llm.provider import LLMProvider, MockProvider


def _use_real_llm() -> bool:
    return settings.llm_provider == "deepseek" and bool(settings.deepseek_api_key)


def get_llm_provider() -> tuple[LLMProvider, bool]:
    if _use_real_llm():
        return DeepSeekProvider(), False
    return MockProvider(), True


def get_scene_classifier() -> SceneClassifier:
    if _use_real_llm():
        return DeepSeekClassifier()
    return MockClassifier()
