"""[2026-07-30] 密码登录路径的测试。

重点不在"密码对了能登进去"，而在几条容易在重构中被悄悄改坏的安全性质：
统一的失败错误码（防手机号枚举）、失败计数锁定、重置密码后旧会话失效。
"""

import pytest
from pydantic import ValidationError

from app.domain.auth import service
from app.domain.auth.passwords import hash_password, verify_password
from app.domain.auth.schemas import (
    PasswordLoginRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
)
from app.infra.repositories import UserRepository

from ._auth_fakes import FakeRedis, FakeSession, make_user

PHONE = "13800000000"


def _patch_lookup(monkeypatch: pytest.MonkeyPatch, user) -> None:  # type: ignore[no-untyped-def]
    """让 UserRepository.get_by_phone_number 返回指定用户（None = 手机号没注册）。"""

    async def _get_by_phone(self, phone_number):  # type: ignore[no-untyped-def]
        return user

    monkeypatch.setattr(UserRepository, "get_by_phone_number", _get_by_phone)


def _patch_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _set_consent(self, user, *, granted, version):  # type: ignore[no-untyped-def]
        user.data_consent = granted
        user.consent_version = version
        return user

    monkeypatch.setattr(UserRepository, "set_data_consent", _set_consent)


# ── 哈希本身 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hash_then_verify_roundtrip() -> None:
    hashed = await hash_password("correct-horse-1")
    assert await verify_password(hashed, "correct-horse-1") is True
    assert await verify_password(hashed, "wrong-password") is False


@pytest.mark.asyncio
async def test_verify_against_missing_hash_is_false() -> None:
    """没设过密码的用户：不能因为传了 None 就意外放行，也不能抛异常。"""
    assert await verify_password(None, "anything") is False


@pytest.mark.asyncio
async def test_same_password_hashes_differently() -> None:
    """argon2 自带随机盐，同一密码两次哈希结果必须不同（否则说明盐没生效）。"""
    assert await hash_password("same-password-1") != await hash_password("same-password-1")


# ── 登录成功路径 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_correct_password_issues_token(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    _patch_consent(monkeypatch)
    redis = FakeRedis()

    token, external_id, ttl = await service.login_with_password(
        FakeSession(),
        redis,
        phone_number=PHONE,
        password="my-password-1",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert token
    assert external_id == user.external_id
    assert ttl > 0
    # token 既要能反查用户，也要登记进该用户的 token 集合（重置密码时要靠它踢人）。
    assert redis.data[f"auth_token:{token}"] == str(user.id)
    assert token in redis.sets[f"user_tokens:{user.id}"]


@pytest.mark.asyncio
async def test_successful_login_clears_failure_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    _patch_consent(monkeypatch)
    redis = FakeRedis()
    redis.data[f"login_fail:{PHONE}"] = "3"

    await service.login_with_password(
        FakeSession(),
        redis,
        phone_number=PHONE,
        password="my-password-1",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert f"login_fail:{PHONE}" not in redis.data


# ── 防枚举：三种失败必须长得一模一样 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_wrong_password_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    redis = FakeRedis()

    with pytest.raises(service.AuthError) as exc:
        await service.login_with_password(
            FakeSession(),
            redis,
            phone_number=PHONE,
            password="not-the-password",
            external_user_id="anon-1",
            agreed_to_terms=True,
        )
    assert exc.value.code == "invalid_credentials"


@pytest.mark.asyncio
async def test_unregistered_phone_and_passwordless_account_look_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """核心安全性质：登录接口不能变成"这个手机号注册没注册"的查询工具。

    手机号不存在 / 存在但没设密码 / 密码输错——三条路径的错误码和提示文案必须完全一致。
    """
    codes = []
    messages = []

    for lookup in (None, make_user(password_hash=None)):
        _patch_lookup(monkeypatch, lookup)
        with pytest.raises(service.AuthError) as exc:
            await service.login_with_password(
                FakeSession(),
                FakeRedis(),
                phone_number=PHONE,
                password="some-password-1",
                external_user_id="anon-1",
                agreed_to_terms=True,
            )
        codes.append(exc.value.code)
        messages.append(str(exc.value))

    assert codes == ["invalid_credentials", "invalid_credentials"]
    assert messages[0] == messages[1]


# ── 暴力破解限流 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failures_accumulate_then_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    redis = FakeRedis()

    for _ in range(service._MAX_LOGIN_FAILURES):
        with pytest.raises(service.AuthError) as exc:
            await service.login_with_password(
                FakeSession(),
                redis,
                phone_number=PHONE,
                password="wrong",
                external_user_id="anon-1",
                agreed_to_terms=True,
            )
        assert exc.value.code == "invalid_credentials"

    # 再试一次：这回是被锁住，而不是继续比对密码。
    with pytest.raises(service.AuthError) as exc:
        await service.login_with_password(
            FakeSession(),
            redis,
            phone_number=PHONE,
            password="wrong",
            external_user_id="anon-1",
            agreed_to_terms=True,
        )
    assert exc.value.code == "too_many_attempts"


@pytest.mark.asyncio
async def test_lockout_blocks_even_the_correct_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """锁定期内即使密码对也要拒——否则限流形同虚设。"""
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    redis = FakeRedis()
    redis.data[f"login_fail:{PHONE}"] = str(service._MAX_LOGIN_FAILURES)

    with pytest.raises(service.AuthError) as exc:
        await service.login_with_password(
            FakeSession(),
            redis,
            phone_number=PHONE,
            password="my-password-1",
            external_user_id="anon-1",
            agreed_to_terms=True,
        )
    assert exc.value.code == "too_many_attempts"


# ── 设置 / 修改密码 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_time_set_password_needs_no_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """还没设过密码时不要求旧密码——持有有效 token 本身就是身份证明。"""
    user = make_user(password_hash=None)
    redis = FakeRedis()
    redis.data["auth_token:tok"] = str(user.id)
    session = FakeSession({user.id: user})

    await service.set_password(
        session, redis, token="tok", current_password=None, new_password="brand-new-1"
    )

    assert user.password_hash is not None
    assert await verify_password(user.password_hash, "brand-new-1") is True


@pytest.mark.asyncio
async def test_changing_existing_password_requires_current() -> None:
    user = make_user(password_hash=await hash_password("old-password-1"))
    redis = FakeRedis()
    redis.data["auth_token:tok"] = str(user.id)
    session = FakeSession({user.id: user})

    with pytest.raises(service.AuthError) as exc:
        await service.set_password(
            session, redis, token="tok", current_password=None, new_password="new-password-1"
        )
    assert exc.value.code == "invalid_credentials"

    with pytest.raises(service.AuthError):
        await service.set_password(
            session, redis, token="tok", current_password="wrong", new_password="new-password-1"
        )

    # 旧密码正确时才真正改掉
    await service.set_password(
        session, redis, token="tok", current_password="old-password-1", new_password="new-password-1"
    )
    assert await verify_password(user.password_hash, "new-password-1") is True


@pytest.mark.asyncio
async def test_set_password_with_invalid_token_rejected() -> None:
    with pytest.raises(service.AuthError) as exc:
        await service.set_password(
            FakeSession(),
            FakeRedis(),
            token="nonexistent",
            current_password=None,
            new_password="whatever-1",
        )
    assert exc.value.code == "unauthorized"


# ── 重置密码 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_password_revokes_all_existing_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """改完密码，其他设备上的登录态必须全部失效。"""
    user = make_user(password_hash=await hash_password("old-password-1"))
    _patch_lookup(monkeypatch, user)
    _patch_consent(monkeypatch)

    redis = FakeRedis()
    # 该用户已经在两台设备上登录过
    for old in ("device-a", "device-b"):
        redis.data[f"auth_token:{old}"] = str(user.id)
        redis.sets.setdefault(f"user_tokens:{user.id}", set()).add(old)
    redis.data[f"verify_code:reset:{PHONE}"] = "123456"

    new_token, _, _ = await service.reset_password(
        FakeSession(),
        redis,
        phone_number=PHONE,
        code="123456",
        new_password="fresh-password-1",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert "auth_token:device-a" not in redis.data
    assert "auth_token:device-b" not in redis.data
    # 重置后新签发的这个要能用
    assert redis.data[f"auth_token:{new_token}"] == str(user.id)
    assert await verify_password(user.password_hash, "fresh-password-1") is True


@pytest.mark.asyncio
async def test_reset_password_clears_lockout(monkeypatch: pytest.MonkeyPatch) -> None:
    """被锁住的人正是最可能来重置密码的人，重置完不该还被锁着。"""
    user = make_user(password_hash=await hash_password("old-password-1"))
    _patch_lookup(monkeypatch, user)
    _patch_consent(monkeypatch)

    redis = FakeRedis()
    redis.data[f"login_fail:{PHONE}"] = str(service._MAX_LOGIN_FAILURES)
    redis.data[f"verify_code:reset:{PHONE}"] = "123456"

    await service.reset_password(
        FakeSession(),
        redis,
        phone_number=PHONE,
        code="123456",
        new_password="fresh-password-1",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert f"login_fail:{PHONE}" not in redis.data


@pytest.mark.asyncio
async def test_reset_rejects_login_purpose_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """为登录发的验证码不能拿来重置密码——两种用途的码分开存。"""
    user = make_user()
    _patch_lookup(monkeypatch, user)
    redis = FakeRedis()
    redis.data[f"verify_code:login:{PHONE}"] = "123456"  # 注意是 login 不是 reset

    with pytest.raises(service.AuthError) as exc:
        await service.reset_password(
            FakeSession(),
            redis,
            phone_number=PHONE,
            code="123456",
            new_password="fresh-password-1",
            external_user_id="anon-1",
            agreed_to_terms=True,
        )
    assert exc.value.code == "invalid_code"


# ── 密码强度规则 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "password",
    [
        "short1",  # 不足 8 位
        "12345678",  # 纯数字
        "1234567890123",  # 纯数字（长一点也不行）
        "x" * 65,  # 超过 64 位
    ],
)
def test_weak_passwords_rejected(password: str) -> None:
    with pytest.raises(ValidationError):
        SetPasswordRequest(new_password=password)


@pytest.mark.parametrize("password", ["passw0rd", "a" * 64, "我的密码abc123"])
def test_acceptable_passwords_pass(password: str) -> None:
    assert SetPasswordRequest(new_password=password).new_password == password


def test_password_must_not_equal_phone_number() -> None:
    with pytest.raises(ValidationError):
        ResetPasswordRequest(
            phone_number=PHONE,
            code="123456",
            new_password=PHONE,
            external_user_id="anon-1",
            agreed_to_terms=True,
        )


def test_login_does_not_enforce_strength_rules() -> None:
    """登录时不校验强度：库里可能有按旧规则设的密码，在这里拦会把人锁在门外。"""
    req = PasswordLoginRequest(
        phone_number=PHONE,
        password="1234",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )
    assert req.password == "1234"
