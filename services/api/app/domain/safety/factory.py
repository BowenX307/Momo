"""按运行时配置选安全 provider。"""

from app.core.config import settings
from app.domain.safety.aliyun import AliyunSafetyProvider
from app.domain.safety.provider import LocalOnlySafetyProvider, SafetyProvider


def get_safety_provider() -> tuple[SafetyProvider, bool]:
    if (
        settings.safety_provider == "aliyun"
        and settings.aliyun_access_key_id
        and settings.aliyun_access_key_secret
    ):
        return AliyunSafetyProvider(), False
    return LocalOnlySafetyProvider(), True
