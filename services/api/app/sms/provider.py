"""短信 provider 抽象层。"""

from typing import Protocol


class SmsError(RuntimeError):
    """短信发送失败时统一抛出。"""

    def __init__(
        self, code: str, message: str, upstream_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status


class SmsProvider(Protocol):
    """短信 provider 接口：发一条验证码短信。"""

    async def send_verification_code(self, phone_number: str, code: str) -> None: ...
