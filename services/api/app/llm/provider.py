"""LLM provider 抽象层。

所有业务代码只依赖 `LLMProvider` Protocol；具体 provider（DeepSeek、Mock 等）
在 `app/llm/factory.py` 里按运行时配置选出。

`MockProvider` 用于本地开发与下周五 demo 兜底：未配置 key、ENV=dev 时默认走它，
保证服务在没有外部依赖时也能跑通整条链路（safety → llm → response）。

`LLMError` 是 provider 层向编排层抛出的统一错误信号。provider 自己不要直接
"降级到 mock"，那是 `domain/conversation/service.py` 的职责（保持单一职责与
可测试性）。
"""

from typing import Protocol


class LLMError(RuntimeError):
    """LLM provider 调用失败时统一抛出，便于上层决定是否降级。

    Attributes:
        code: 机器可读错误码（如 "timeout" / "http_status" / "decode" / "unknown"），
            进日志便于事后分析；不向最终用户暴露。
        upstream_status: 若来自非 200 响应，记录原始 HTTP 状态码；否则 None。
    """

    def __init__(
        self, code: str, message: str, upstream_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status


class LLMProvider(Protocol):
    """LLM provider 接口。所有 provider 必须实现该签名。

    刻意保留极简签名（scene + user_text → str），后续多轮、工具调用再扩展。
    """

    async def complete(self, scene: str, user_text: str) -> str: ...


class MockProvider:
    """固定回复的 mock provider，用于 demo 与离线开发。

    回复模板按 scene 做轻微差异，便于前端肉眼区分是否传对场景。
    """

    _SCENE_TEMPLATES: dict[str, str] = {
        "late_night": "现在是深夜，慢慢说，我陪你。{echo}这件事在你心里挺重的吧。",
        "rumination": "你又在心里反复过这件事了。{echo}我们先把它放一放，呼吸一下。",
        "relationship": "听起来这段关系让你很消耗。{echo}你愿意多说一点是怎么走到这一步的吗？",
        "stress": "压力堆到这种程度，能撑到现在已经不容易。{echo}先告诉我现在身体哪里最紧。",
        "loneliness": "孤独的时候，连小事都会变得很大。{echo}我在这儿，慢慢说没关系。",
    }

    _DEFAULT_TEMPLATE = "我在听。{echo}你愿意多说一点吗？"

    async def complete(self, scene: str, user_text: str) -> str:
        template = self._SCENE_TEMPLATES.get(scene, self._DEFAULT_TEMPLATE)
        echo = f"你说「{user_text.strip()[:40]}」，" if user_text.strip() else ""
        return template.format(echo=echo)
