"""[2026-07-30] 协议同意的测试。

产品决定：协议门槛只卡在注册/登录这一层，匿名访客不受影响。所以这里既要锁住
"登录必须同意"，也要锁住"同意状态确实落库"——那三个字段在库里躺了很久一直没人写，
容易在后续重构中又被漏掉。
"""

import pytest

from app.domain.auth import service
from app.domain.auth.passwords import hash_password
from app.infra.repositories import UserRepository

from ._auth_fakes import FakeRedis, FakeSession, make_user

PHONE = "13800000000"


def _patch_lookup(monkeypatch: pytest.MonkeyPatch, user) -> None:  # type: ignore[no-untyped-def]
    async def _get_by_phone(self, phone_number):  # type: ignore[no-untyped-def]
        return user

    monkeypatch.setattr(UserRepository, "get_by_phone_number", _get_by_phone)


def _patch_consent_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    """用真实签名的替身记录 set_data_consent 收到的参数。"""

    async def _set_consent(self, user, *, granted, version):  # type: ignore[no-untyped-def]
        user.data_consent = granted
        user.consent_version = version
        return user

    monkeypatch.setattr(UserRepository, "set_data_consent", _set_consent)


# ── 未同意时必须拒绝 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_code_rejects_without_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    redis.data[f"verify_code:login:{PHONE}"] = "123456"

    with pytest.raises(service.AuthError) as exc:
        await service.verify_code(
            FakeSession(),
            redis,
            phone_number=PHONE,
            code="123456",
            external_user_id="anon-1",
            agreed_to_terms=False,
        )
    assert exc.value.code == "terms_required"


@pytest.mark.asyncio
async def test_rejected_consent_leaves_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没同意就退出，必须发生在任何写操作之前：不签 token，连验证码都不该被消耗掉。"""
    redis = FakeRedis()
    redis.data[f"verify_code:login:{PHONE}"] = "123456"
    session = FakeSession()

    with pytest.raises(service.AuthError):
        await service.verify_code(
            session,
            redis,
            phone_number=PHONE,
            code="123456",
            external_user_id="anon-1",
            agreed_to_terms=False,
        )

    assert session.commits == 0
    # 验证码还在——用户勾上协议后可以直接重试，不用再等一条短信。
    assert redis.data[f"verify_code:login:{PHONE}"] == "123456"
    assert not any(k.startswith("auth_token:") for k in redis.data)


@pytest.mark.asyncio
async def test_password_login_rejects_without_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    redis = FakeRedis()

    with pytest.raises(service.AuthError) as exc:
        await service.login_with_password(
            FakeSession(),
            redis,
            phone_number=PHONE,
            password="my-password-1",
            external_user_id="anon-1",
            agreed_to_terms=False,
        )
    assert exc.value.code == "terms_required"
    # 没同意时连密码都不该比对，失败计数自然也不该涨。
    assert f"login_fail:{PHONE}" not in redis.data


@pytest.mark.asyncio
async def test_reset_password_rejects_without_consent() -> None:
    redis = FakeRedis()
    redis.data[f"verify_code:reset:{PHONE}"] = "123456"

    with pytest.raises(service.AuthError) as exc:
        await service.reset_password(
            FakeSession(),
            redis,
            phone_number=PHONE,
            code="123456",
            new_password="fresh-password-1",
            external_user_id="anon-1",
            agreed_to_terms=False,
        )
    assert exc.value.code == "terms_required"


# ── 同意后必须落库 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_code_records_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user()
    _patch_lookup(monkeypatch, user)
    _patch_consent_recording(monkeypatch)

    redis = FakeRedis()
    redis.data[f"verify_code:login:{PHONE}"] = "123456"
    session = FakeSession()

    await service.verify_code(
        session,
        redis,
        phone_number=PHONE,
        code="123456",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert user.data_consent is True
    assert user.consent_version == service.TERMS_VERSION
    assert session.commits == 1


@pytest.mark.asyncio
async def test_password_login_records_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    """密码登录也要记——协议改版后，只用密码登录的人同样应该被重新收集同意。"""
    user = make_user(password_hash=await hash_password("my-password-1"))
    _patch_lookup(monkeypatch, user)
    _patch_consent_recording(monkeypatch)

    await service.login_with_password(
        FakeSession(),
        FakeRedis(),
        phone_number=PHONE,
        password="my-password-1",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert user.data_consent is True
    assert user.consent_version == service.TERMS_VERSION


@pytest.mark.asyncio
async def test_consent_version_is_written_not_hardcoded_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """记的是"同意了哪一版"，不只是"同意了"——协议改版时要靠版本号筛出待重新同意的人。"""
    user = make_user()
    _patch_lookup(monkeypatch, user)

    seen: dict = {}

    async def _spy(self, u, *, granted, version):  # type: ignore[no-untyped-def]
        seen["granted"] = granted
        seen["version"] = version
        return u

    monkeypatch.setattr(UserRepository, "set_data_consent", _spy)

    redis = FakeRedis()
    redis.data[f"verify_code:login:{PHONE}"] = "123456"
    await service.verify_code(
        FakeSession(),
        redis,
        phone_number=PHONE,
        code="123456",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )

    assert seen == {"granted": True, "version": service.TERMS_VERSION}


# ── 验证码用途隔离 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_rejects_reset_purpose_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """为重置密码发的码不能拿来登录（反向的用例在 test_auth_password.py）。"""
    redis = FakeRedis()
    redis.data[f"verify_code:reset:{PHONE}"] = "123456"

    with pytest.raises(service.AuthError) as exc:
        await service.verify_code(
            FakeSession(),
            redis,
            phone_number=PHONE,
            code="123456",
            external_user_id="anon-1",
            agreed_to_terms=True,
        )
    assert exc.value.code == "invalid_code"


@pytest.mark.asyncio
async def test_code_is_consumed_after_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """一个验证码只能用一次。"""
    user = make_user()
    _patch_lookup(monkeypatch, user)
    _patch_consent_recording(monkeypatch)

    redis = FakeRedis()
    redis.data[f"verify_code:login:{PHONE}"] = "123456"

    await service.verify_code(
        FakeSession(),
        redis,
        phone_number=PHONE,
        code="123456",
        external_user_id="anon-1",
        agreed_to_terms=True,
    )
    assert f"verify_code:login:{PHONE}" not in redis.data

    with pytest.raises(service.AuthError) as exc:
        await service.verify_code(
            FakeSession(),
            redis,
            phone_number=PHONE,
            code="123456",
            external_user_id="anon-1",
            agreed_to_terms=True,
        )
    assert exc.value.code == "invalid_code"


# ── 可观测性：手机号脱敏 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("13061669307", "130****9307"),
        ("18918696667", "189****6667"),
        ("", "***"),
        ("12345", "***"),
    ],
)
def test_mask_phone(phone: str, expected: str) -> None:
    """日志里要能定位是哪个号，又不能落完整手机号。"""
    assert service.mask_phone(phone) == expected


def test_mask_phone_never_leaks_middle_digits() -> None:
    """中间四位是运营商号段之后最敏感的部分，必须被盖掉。"""
    masked = service.mask_phone("13061669307")

    assert "1669" not in masked
    assert masked.count("*") == 4
