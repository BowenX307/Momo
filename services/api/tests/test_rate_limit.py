"""[2026-08-01] 限流与验证码猜错次数上限的测试。

背景：verify-code 原先猜错什么都不做，6 位验证码(100 万种) + 5 分钟有效期 + 接口无限流
= 可暴力破解并拿到合法 token。这里锁住两道防线：单个验证码能被试几次，以及单位时间能
发起多少次尝试。
"""

import pytest
from fastapi import HTTPException

from app.api.v1.deps import client_ip, enforce_rate_limit
from app.core.config import settings
from app.domain.auth import service as auth_service
from app.infra.rate_limit import allow


class _FakeRedis:
    """够用的内存版 Redis：只实现被测代码用到的几个命令。"""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.store: dict[str, int | str] = dict(initial or {})
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = int(self.store.get(key, 0)) + 1
        return int(self.store[key])

    async def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.expires.get(key, -1)

    async def get(self, key: str) -> str | None:
        value = self.store.get(key)
        return None if value is None else str(value)

    async def delete(self, key: str) -> int:
        self.store.pop(key, None)
        self.expires.pop(key, None)
        return 1


class _BrokenRedis:
    async def incr(self, key: str) -> int:
        raise RuntimeError("redis down")


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, host: str = "1.2.3.4"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})()


# ── 计数器本身 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_allow_permits_up_to_limit_then_blocks() -> None:
    redis = _FakeRedis()

    results = [
        await allow(redis, key="k", limit=3, window_seconds=60) for _ in range(5)
    ]

    assert results == [True, True, True, False, False]


@pytest.mark.asyncio
async def test_allow_sets_expiry_only_on_first_hit() -> None:
    """每次都刷新过期时间的话，持续打请求的人会把窗口无限延长、永远解不了封。"""
    redis = _FakeRedis()

    await allow(redis, key="k", limit=10, window_seconds=60)
    redis.expires["k"] = 5  # 模拟窗口已经走过一段
    await allow(redis, key="k", limit=10, window_seconds=60)

    assert redis.expires["k"] == 5, "第二次不应重置窗口"


@pytest.mark.asyncio
async def test_allow_recovers_when_expiry_was_lost() -> None:
    """兜底：上次 expire 没设上时要补设，否则 key 永久存在、把人永久挡在外面。"""
    redis = _FakeRedis({"k": 5})  # 有计数但没有 TTL

    await allow(redis, key="k", limit=10, window_seconds=60)

    assert redis.expires["k"] == 60


@pytest.mark.asyncio
async def test_allow_fails_open_when_redis_is_down() -> None:
    """限流是保护措施，不该因为它自己挂了就让聊天整体不可用。"""
    assert await allow(_BrokenRedis(), key="k", limit=1, window_seconds=60) is True


# ── 真实 IP 提取 ────────────────────────────────────────────────────────


def test_client_ip_prefers_last_forwarded_entry() -> None:
    """客户端能伪造整个 XFF 头，nginx 把真实来源追加在末尾，所以取末尾那个。"""
    request = _FakeRequest({"x-forwarded-for": "9.9.9.9, 203.0.113.7"})

    assert client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_socket_peer() -> None:
    assert client_ip(_FakeRequest()) == "1.2.3.4"


# ── 接口层 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_raises_429_after_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_ip_multiplier", 100)  # 只测身份桶
    redis = _FakeRedis()
    request = _FakeRequest()

    for _ in range(2):
        await enforce_rate_limit(
            request, redis, bucket="chat", limit=2, identity="user-a"
        )

    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit(
            request, redis, bucket="chat", limit=2, identity="user-a"
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rotating_identity_still_caught_by_ip_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """external_user_id 由客户端生成，换一个就能绕过身份桶，IP 桶用来兜住这种轮换。"""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_ip_multiplier", 2)
    redis = _FakeRedis()
    request = _FakeRequest()

    for i in range(2):
        await enforce_rate_limit(
            request, redis, bucket="chat", limit=1, identity=f"rotating-{i}"
        )

    with pytest.raises(HTTPException):
        await enforce_rate_limit(
            request, redis, bucket="chat", limit=1, identity="rotating-99"
        )


@pytest.mark.asyncio
async def test_disabled_switch_skips_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    for _ in range(50):
        await enforce_rate_limit(
            _FakeRequest(), _BrokenRedis(), bucket="chat", limit=1, identity="u"
        )


# ── 验证码猜错次数上限 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_code_invalidates_code_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """猜错到上限后验证码本身作废，逼对方重新发码(发码侧有每日上限)。"""
    monkeypatch.setattr(settings, "verify_code_max_attempts", 3)
    redis = _FakeRedis({"verify_code:13800000000": "123456"})

    for _ in range(2):
        with pytest.raises(auth_service.AuthError) as exc:
            await auth_service.verify_code(
                session=None,
                redis=redis,
                phone_number="13800000000",
                code="000000",
                external_user_id="anon-1",
            )
        assert exc.value.code == "invalid_code"

    with pytest.raises(auth_service.AuthError) as exc:
        await auth_service.verify_code(
            session=None,
            redis=redis,
            phone_number="13800000000",
            code="000000",
            external_user_id="anon-1",
        )
    assert exc.value.code == "too_many_attempts"

    # 关键：正确的验证码此后也不再可用，必须重新发送。
    assert await redis.get("verify_code:13800000000") is None
