"""安全 provider 单元测试。"""

import json

import httpx
import pytest
import respx

from app.core.config import settings
from app.domain.safety.aliyun import AliyunSafetyProvider
from app.domain.safety.provider import LocalOnlySafetyProvider


def _aliyun_response(label: str, risk_level: str = "high") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "Code": 200,
            "Data": {
                "RiskLevel": risk_level,
                "Result": [
                    {
                        "Label": label,
                        "Confidence": 99.0,
                    }
                ],
            },
            "Message": "OK",
            "RequestId": "test-request-id",
        },
    )


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
    assert result.reason == "illegal_keyword"
    assert "不能继续展开" in result.fallback_text


@pytest.mark.asyncio
async def test_aliyun_safety_provider_maps_hate_label_to_hate_reason(
    monkeypatch,
):
    monkeypatch.setattr(settings, "aliyun_access_key_id", "testid")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "testsecret")
    provider = AliyunSafetyProvider()
    url = f"{settings.aliyun_safety_base_url}/"

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(url).mock(
            return_value=_aliyun_response("inappropriate_profanity")
        )
        result = await provider.check("这是测试文本")

    url_params = route.calls.last.request.url.params
    service_params = json.loads(url_params["ServiceParameters"])
    assert url_params["Service"] == settings.aliyun_safety_service
    assert service_params["content"] == "这是测试文本"
    assert url_params["Signature"]
    assert result.decision == "fallback"
    assert result.reason == "hate_discrimination_keyword"
    assert "不能顺着继续" in result.fallback_text
    assert "心理援助热线" not in result.fallback_text
    assert "信任的人" not in result.fallback_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "expected_reason", "expected_text"),
    [
        ("violent_weapons", "illegal_keyword", "不能继续展开"),
        ("contraband_drug", "illegal_keyword", "不能继续展开"),
        ("pornographic_adult_activity", "low_quality_keyword", "换一种说法"),
        ("sexual_terms_offend", "low_quality_keyword", "换一种说法"),
        ("inappropriate_suicide", "crisis_keyword", "心理援助热线"),
        ("unknown_future_label", "aliyun_keyword", "换个轻一点的话题"),
    ],
)
async def test_aliyun_safety_provider_maps_labels_to_layered_reasons(
    monkeypatch,
    label: str,
    expected_reason: str,
    expected_text: str,
):
    monkeypatch.setattr(settings, "aliyun_access_key_id", "testid")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "testsecret")
    provider = AliyunSafetyProvider()
    url = f"{settings.aliyun_safety_base_url}/"

    with respx.mock(assert_all_called=True) as mock:
        mock.post(url).mock(return_value=_aliyun_response(label))
        result = await provider.check("这是测试文本")

    assert result.decision == "fallback"
    assert result.reason == expected_reason
    assert expected_text in result.fallback_text


@pytest.mark.asyncio
async def test_aliyun_safety_provider_allows_low_risk_label(monkeypatch):
    monkeypatch.setattr(settings, "aliyun_access_key_id", "testid")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "testsecret")
    provider = AliyunSafetyProvider()
    url = f"{settings.aliyun_safety_base_url}/"

    with respx.mock(assert_all_called=True) as mock:
        mock.post(url).mock(
            return_value=_aliyun_response("violent_weapons", risk_level="low")
        )
        result = await provider.check("这是测试文本")

    assert result.decision == "allow"
    assert result.reason == "ok"


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
