"""[2026-07-30] 登录路由的 HTTP 层测试。

service 层的单测覆盖了逻辑本身，这里只管**接线**：路由有没有把参数原样传下去、
AuthError 的 code 有没有映射成对的 HTTP 状态、响应体结构对不对。

用 dependency_overrides 顶掉 DB / Redis（沿用 test_conversation_history_auth.py 的做法），
service 层整个 monkeypatch 掉——这层不重复验证业务逻辑。
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.domain.auth import service
from app.infra.database import get_db_session
from app.infra.redis_client import get_redis

PHONE = "13800000000"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = main_module.app
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_redis] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _login_payload(**overrides) -> dict:  # type: ignore[no-untyped-def]
    payload = {
        "phone_number": PHONE,
        "password": "my-password-1",
        "external_user_id": "anon-1",
        "agreed_to_terms": True,
    }
    payload.update(overrides)
    return payload


# ── 成功路径 ────────────────────────────────────────────────────────────


def test_password_login_returns_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_login(session, redis, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["phone_number"] == PHONE
        assert kwargs["password"] == "my-password-1"
        assert kwargs["agreed_to_terms"] is True
        return ("tok-123", "user-abc", 2592000)

    monkeypatch.setattr(service, "login_with_password", _fake_login)

    response = client.post("/v1/auth/login-password", json=_login_payload())

    assert response.status_code == 200
    assert response.json() == {
        "token": "tok-123",
        "external_user_id": "user-abc",
        "expires_in_seconds": 2592000,
    }


def test_send_code_forwards_purpose(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """purpose 必须原样传到 service —— 传丢了会导致重置密码的码被当成登录码存。"""
    seen: dict = {}

    async def _fake_send(redis, sms_provider, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)

    monkeypatch.setattr(service, "send_code", _fake_send)

    response = client.post(
        "/v1/auth/send-code", json={"phone_number": PHONE, "purpose": "reset"}
    )

    assert response.status_code == 200
    assert seen["purpose"] == "reset"


def test_send_code_defaults_to_login_purpose(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """老前端不带 purpose 时要落到 login，保持向后兼容。"""
    seen: dict = {}

    async def _fake_send(redis, sms_provider, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)

    monkeypatch.setattr(service, "send_code", _fake_send)

    client.post("/v1/auth/send-code", json={"phone_number": PHONE})
    assert seen["purpose"] == "login"


# ── 错误码 → HTTP 状态映射 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("invalid_credentials", 401),
        ("too_many_attempts", 429),
        ("terms_required", 400),
        ("unauthorized", 401),
    ],
)
def test_auth_error_codes_map_to_http_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    expected_status: int,
) -> None:
    async def _fail(session, redis, **kwargs):  # type: ignore[no-untyped-def]
        raise service.AuthError(code, "nope")

    monkeypatch.setattr(service, "login_with_password", _fail)

    response = client.post("/v1/auth/login-password", json=_login_payload())

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == code


def test_unknown_error_code_falls_back_to_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail(session, redis, **kwargs):  # type: ignore[no-untyped-def]
        raise service.AuthError("something_new", "nope")

    monkeypatch.setattr(service, "login_with_password", _fail)

    assert client.post("/v1/auth/login-password", json=_login_payload()).status_code == 400


# ── 请求校验 ────────────────────────────────────────────────────────────


def test_agreed_to_terms_is_required_field(client: TestClient) -> None:
    """漏传 agreed_to_terms 要 422，不能默认成 True 把协议门槛绕过去。"""
    payload = _login_payload()
    del payload["agreed_to_terms"]
    assert client.post("/v1/auth/login-password", json=payload).status_code == 422


def test_malformed_phone_rejected(client: TestClient) -> None:
    assert (
        client.post(
            "/v1/auth/login-password", json=_login_payload(phone_number="12345")
        ).status_code
        == 422
    )


def test_weak_new_password_rejected_by_schema(client: TestClient) -> None:
    """强度规则在 schema 层就拦下，不会走到 service。"""
    response = client.post(
        "/v1/auth/reset-password",
        json={
            "phone_number": PHONE,
            "code": "123456",
            "new_password": "12345678",  # 纯数字
            "external_user_id": "anon-1",
            "agreed_to_terms": True,
        },
    )
    assert response.status_code == 422


# ── set-password 的鉴权 ─────────────────────────────────────────────────


def test_set_password_without_token_is_401(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/set-password",
        json={"current_password": None, "new_password": "brand-new-1"},
    )
    assert response.status_code == 401


def test_set_password_passes_bearer_token_through(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    async def _fake_set(session, redis, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)

    monkeypatch.setattr(service, "set_password", _fake_set)

    response = client.post(
        "/v1/auth/set-password",
        json={"current_password": "old-password-1", "new_password": "brand-new-1"},
        headers={"Authorization": "Bearer tok-abc"},
    )

    assert response.status_code == 204
    assert seen["token"] == "tok-abc"
    assert seen["current_password"] == "old-password-1"
    assert seen["new_password"] == "brand-new-1"


# ── /me ─────────────────────────────────────────────────────────────────


def test_me_reports_password_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """前端靠 has_password 决定显示「设置密码」还是「修改密码」。"""

    class _User:
        external_id = "user-abc"
        phone_number = PHONE
        password_hash = "$argon2id$whatever"
        consent_version = "v1"

    async def _fake_resolve(session, redis, *, token):  # type: ignore[no-untyped-def]
        return _User()

    monkeypatch.setattr(service, "resolve_token_user", _fake_resolve)

    response = client.get("/v1/auth/me", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["has_password"] is True
    assert body["consent_version"] == "v1"


def test_me_reports_no_password_when_unset(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _User:
        external_id = "user-abc"
        phone_number = PHONE
        password_hash = None
        consent_version = None

    async def _fake_resolve(session, redis, *, token):  # type: ignore[no-untyped-def]
        return _User()

    monkeypatch.setattr(service, "resolve_token_user", _fake_resolve)

    response = client.get("/v1/auth/me", headers={"Authorization": "Bearer tok"})
    assert response.json()["has_password"] is False


def test_me_without_token_is_401(client: TestClient) -> None:
    assert client.get("/v1/auth/me").status_code == 401
