"""无短信签名/模板/权限时的 mock：不真的发短信，把验证码打进日志方便本地联调。"""

import structlog

logger = structlog.get_logger(__name__)


class MockSmsProvider:
    """开发环境默认走这个，验证码直接打日志，不花钱不依赖阿里云权限。"""

    async def send_verification_code(self, phone_number: str, code: str) -> None:
        logger.info("mock_sms_send", phone_number=phone_number, code=code)
