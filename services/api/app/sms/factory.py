"""按运行时配置选短信 provider。"""

from app.core.config import settings
from app.sms.aliyun import AliyunSmsProvider
from app.sms.mock import MockSmsProvider
from app.sms.provider import SmsProvider


def get_sms_provider() -> tuple[SmsProvider, bool]:
    """返回 (provider, is_mock)。签名/模板/key 没配全之前，自动落 mock。"""
    if (
        settings.sms_provider == "aliyun"
        and settings.aliyun_sms_access_key_id
        and settings.aliyun_sms_access_key_secret
        and settings.aliyun_sms_sign_name
        and settings.aliyun_sms_template_code
    ):
        return AliyunSmsProvider(), False
    return MockSmsProvider(), True
