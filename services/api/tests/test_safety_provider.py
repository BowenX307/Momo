"""安全 provider 单元测试。"""

import json

import httpx
import pytest
import respx

from app.core.config import settings
from app.domain.safety.aliyun import AliyunSafetyProvider
from app.domain.safety.provider import LocalOnlySafetyProvider


@pytest.mark.asyncio
async def test_local_only_safety_provider_blocks_crisis_keyword():
    provider = LocalOnlySafetyProvider()
    result = await provider.check("我想自杀")

    assert result.decision == "fallback"
    assert result.reason == "crisis_keyword"
    assert "拨打 24 小时心理援助热线" in result.fallback_text


@pytest.mark.asyncio
async def test_local_only_safety_provider_allows_normal_text():
    provider = LocalOnlySafetyProvider()
    result = await provider.check("我今天心情一般")

    assert result.decision == "allow"
    assert result.reason == "ok"


@pytest.mark.asyncio
async def test_local_only_safety_provider_blocks_blocked_keyword():
    provider = LocalOnlySafetyProvider()
    result = await provider.check("这里有炸弹")

    assert result.decision == "fallback"
    assert result.reason == "blocked_keyword"
    assert "换个轻一点的话题" in result.fallback_text


@pytest.mark.asyncio
async def test_aliyun_safety_provider_blocks_on_remote_suggestion_with_blocked_fallback(
    monkeypatch,
):
    monkeypatch.setattr(settings, "aliyun_access_key_id", "testid")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "testsecret")
    provider = AliyunSafetyProvider()
    url = f"{settings.aliyun_safety_base_url}/"

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "Code": 200,
                    "Data": {
                        "RiskLevel": "high",
                        "Result": [
                            {
                                "Label": "inappropriate_profanity",
                                "Confidence": 99.0,
                            }
                        ],
                    },
                    "Message": "OK",
                    "RequestId": "test-request-id",
                },
            )
        )
        result = await provider.check("这是测试文本")

    url_params = route.calls.last.request.url.params
    service_params = json.loads(url_params["ServiceParameters"])
    assert url_params["Service"] == settings.aliyun_safety_service
    assert service_params["content"] == "这是测试文本"
    assert url_params["Signature"]
    assert result.decision == "fallback"
    assert result.reason == "aliyun_keyword"
    assert "换个轻一点的话题" in result.fallback_text
    assert "心理援助热线" not in result.fallback_text
    assert "信任的人" not in result.fallback_text


@pytest.mark.asyncio
async def test_aliyun_safety_provider_fails_open_on_timeout(monkeypatch):
    monkeypatch.setattr(settings, "aliyun_access_key_id", "testid")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "testsecret")
    provider = AliyunSafetyProvider()
    url = f"{settings.aliyun_safety_base_url}/"

    with respx.mock(assert_all_called=True) as mock:
        mock.post(url).mock(side_effect=httpx.TimeoutException("timeout"))
        result = await provider.check("这是测试文本")

    assert result.decision == "allow"
    assert result.reason == "ok"
