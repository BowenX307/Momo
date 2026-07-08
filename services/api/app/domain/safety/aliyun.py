"""阿里云内容安全 provider。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from base64 import b64encode
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.domain.safety.provider import LocalOnlySafetyProvider, SafetyProvider
from app.domain.safety.rules import SafetyResult, blocked_fallback_text

logger = logging.getLogger(__name__)


class AliyunSafetyProvider(LocalOnlySafetyProvider):
    """阿里云安全 provider。

    本地关键词规则优先；只有本地判断允许后才调用阿里云检查。
    远端调用失败时采用 fail_open=True，避免把安全层变成可用性瓶颈。
    """

    async def check(self, text: str) -> SafetyResult:
        local = await super().check(text)
        if not local.allowed:
            return local
        if not (settings.aliyun_access_key_id and settings.aliyun_access_key_secret):
            return local

        return await self._check_remote(text)

    async def _check_remote(self, text: str) -> SafetyResult:
        url = f"{settings.aliyun_safety_base_url}/"
        params = self._build_rpc_params()
        params["Service"] = settings.aliyun_safety_service
        params["ServiceParameters"] = json.dumps(
            {
                "content": text,
                "dataId": uuid.uuid4().hex,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        params["Signature"] = self._sign("POST", "/", params)
        headers = {
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.safety_timeout_seconds
            ) as client:
                response = await client.post(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("aliyun_safety_timeout: %s", exc)
            return SafetyResult(decision="allow", reason="ok")
        except httpx.HTTPError as exc:
            logger.warning("aliyun_safety_http_error: %s", exc)
            return SafetyResult(decision="allow", reason="ok")

        if response.status_code != 200:
            logger.warning(
                "aliyun_safety_non_200 status=%s body=%s",
                response.status_code,
                response.text,
            )
            return SafetyResult(decision="allow", reason="ok")

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("aliyun_safety_decode_error: %s", exc)
            return SafetyResult(decision="allow", reason="ok")

        code = data.get("Code", data.get("code"))
        if code != 200:
            logger.warning(
                "aliyun_safety_bad_code code=%s data=%s",
                code,
                data,
            )
            return SafetyResult(decision="allow", reason="ok")

        result_data = data.get("Data", data.get("data")) or {}
        risk_level = str(result_data.get("RiskLevel", "")).lower()
        if risk_level in {"high", "medium"}:
            return SafetyResult(
                decision="fallback",
                reason="aliyun_keyword",
                fallback_text=blocked_fallback_text(),
            )

        return SafetyResult(decision="allow", reason="ok")

    def _build_rpc_params(self) -> dict[str, str]:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {
            "Format": "JSON",
            "Version": settings.aliyun_safety_api_version,
            "AccessKeyId": settings.aliyun_access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": timestamp,
            "SignatureVersion": "1.0",
            "SignatureNonce": uuid.uuid4().hex,
            "RegionId": settings.aliyun_region_id,
            "Action": "TextModerationPlus",
        }

    def _percent_encode(self, value: str) -> str:
        return quote(str(value), safe="~")

    def _sign(self, method: str, path: str, params: dict[str, str]) -> str:
        canonicalized = "&".join(
            f"{self._percent_encode(key)}={self._percent_encode(value)}"
            for key, value in sorted(params.items())
        )
        string_to_sign = (
            f"{method}&{self._percent_encode(path)}&{self._percent_encode(canonicalized)}"
        )
        key = f"{settings.aliyun_access_key_secret}&"
        signed = hmac.new(
            key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1
        )
        return b64encode(signed.digest()).decode("utf-8")
