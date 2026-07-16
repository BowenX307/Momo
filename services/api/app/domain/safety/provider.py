"""安全 provider 抽象层。"""

from typing import Protocol

from app.domain.safety.rules import SafetyResult, check as local_check


class SafetyProvider(Protocol):
    """安全 provider 接口。"""

    async def check(self, text: str) -> SafetyResult: ...


class LocalOnlySafetyProvider:
    """本地关键词规则 provider。"""

    async def check(self, text: str) -> SafetyResult:
        return local_check(text)


MockSafetyProvider = LocalOnlySafetyProvider
