"""阿里云短信服务 SendSms——手写 RPC 签名(HMAC-SHA1),不引入官方 SDK。

阿里云开放 API 用的是老式 RPC 签名机制(dysmsapi 2017-05-25 版)，官方 SDK
(alibabacloud_dysmsapi20170525)会带一串依赖(cryptography 等 30 来个包)，这里手写
签名，保持和项目里其它 provider(deepseek.py/doubao.py/aliyun 内容安全)一样
"自包含 httpx 调用"的风格，不额外引入 SDK 依赖树。
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.sms.provider import SmsError

_ENDPOINT = "https://dysmsapi.aliyuncs.com/"
_API_VERSION = "2017-05-25"


def _percent_encode(value: str) -> str:
    """阿里云 RPC 签名要求的 percent-encode。

    Python 的 quote(safe="") 本身已经是标准 RFC3986 编码(空格→%20、*→%2A、
    ~ 不编码)，下面几个 replace 是阿里云文档给的通用修正步骤，对 Python 是
    no-op，保留是为了和官方文档描述的算法对齐、方便以后核对。
    """
    encoded = quote(value, safe="")
    return encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _canonical_query_string(params: dict[str, str]) -> str:
    items = sorted(params.items())
    return "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in items)


def _sign(params: dict[str, str], secret: str, method: str = "GET") -> str:
    canonical = _canonical_query_string(params)
    string_to_sign = f"{method}&{_percent_encode('/')}&{_percent_encode(canonical)}"
    digest = hmac.new(
        f"{secret}&".encode(), string_to_sign.encode(), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode()


class AliyunSmsProvider:
    """真实发送验证码短信；失败统一抛 SmsError。"""

    async def send_verification_code(self, phone_number: str, code: str) -> None:
        params = {
            "AccessKeyId": settings.aliyun_sms_access_key_id,
            "Action": "SendSms",
            "Format": "JSON",
            "PhoneNumbers": phone_number,
            "RegionId": settings.aliyun_sms_region_id,
            "SignName": settings.aliyun_sms_sign_name,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid.uuid4().hex,
            "SignatureVersion": "1.0",
            "TemplateCode": settings.aliyun_sms_template_code,
            "TemplateParam": json.dumps({"code": code}, ensure_ascii=False),
            "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": _API_VERSION,
        }
        params["Signature"] = _sign(params, settings.aliyun_sms_access_key_secret)

        try:
            async with httpx.AsyncClient(timeout=settings.sms_timeout_seconds) as client:
                response = await client.get(_ENDPOINT, params=params)
        except httpx.TimeoutException as exc:
            raise SmsError("timeout", f"sms timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise SmsError("network", f"sms network error: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code != 200 or body.get("Code") != "OK":
            raise SmsError(
                str(body.get("Code", "unknown")),
                f"sms send failed: {body.get('Message', response.text[:200])}",
                upstream_status=response.status_code,
            )
