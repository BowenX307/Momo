"""安全 provider factory 单元测试。"""

import pytest

from app.core.config import settings
from app.domain.safety.aliyun import AliyunSafetyProvider
from app.domain.safety.factory import get_safety_provider
from app.domain.safety.provider import LocalOnlySafetyProvider


def test_get_safety_provider_returns_local_when_mock_selected(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "mock")
    provider, is_mock = get_safety_provider()

    assert isinstance(provider, LocalOnlySafetyProvider)
    assert is_mock is True


def test_get_safety_provider_returns_local_when_aliyun_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "aliyun")
    monkeypatch.setattr(settings, "aliyun_access_key_id", "")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "")
    provider, is_mock = get_safety_provider()

    assert isinstance(provider, LocalOnlySafetyProvider)
    assert is_mock is True


def test_get_safety_provider_returns_aliyun_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "aliyun")
    monkeypatch.setattr(settings, "aliyun_access_key_id", "testid")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "testsecret")
    provider, is_mock = get_safety_provider()

    assert isinstance(provider, AliyunSafetyProvider)
    assert is_mock is False
