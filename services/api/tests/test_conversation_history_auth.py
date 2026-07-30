"""[2026-07-29] 历史轮次接口的身份裁决测试。

原先 /v1/conversation/rounds 只看 query 里的 external_user_id，不做验证——给一个 ID
就能读到那个人的全部对话记录。这里锁住收紧后的行为：带有效 token 时以 token 身份为准，
匿名请求维持原行为。
"""

import pytest
from fastapi.testclient import TestClient

import app.api.v1.conversation as conversation_route
import app.main as main_module
from app.api.v1.deps import (
    optional_authenticated_user_id,
    resolve_owner_id,
)
from app.domain.auth import service as auth_service
from app.infra.database import get_db_session


# ── resolve_owner_id：纯函数，覆盖三种组合 ──────────────────────────────


def test_anonymous_request_keeps_claimed_id() -> None:
    """没有 token 时维持原行为，直接用请求里的 ID（匿名态仍需可用）。"""
    assert resolve_owner_id(None, "anon-123") == "anon-123"


def test_token_identity_wins_when_it_matches() -> None:
    """正常登录：token 身份与请求里的一致。"""
    assert resolve_owner_id("user-abc", "user-abc") == "user-abc"


def test_token_identity_wins_over_mismatched_claim() -> None:
    """核心安全属性：请求里指向别人时，仍只按 token 自己的身份读。"""
    assert resolve_owner_id("attacker-self", "victim-id") == "attacker-self"


# ── 依赖本身：Authorization 头的各种情况 ────────────────────────────────


@pytest.mark.asyncio
async def test_missing_authorization_header_returns_none() -> None:
    result = await optional_authenticated_user_id(
        session=object(), redis=object(), authorization=None
    )
    assert result is None


@pytest.mark.asyncio
async def test_blank_bearer_token_returns_none() -> None:
    result = await optional_authenticated_user_id(
        session=object(), redis=object(), authorization="Bearer   "
    )
    assert result is None


@pytest.mark.asyncio
async def test_valid_token_resolves_to_its_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_resolve(session, redis, *, token):  # type: ignore[no-untyped-def]
        assert token == "good-token"
        return ("user-from-token", "13800000000")

    monkeypatch.setattr(auth_service, "resolve_token", _fake_resolve)

    result = await optional_authenticated_user_id(
        session=object(), redis=object(), authorization="Bearer good-token"
    )
    assert result == "user-from-token"


@pytest.mark.asyncio
async def test_invalid_token_falls_back_to_anonymous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """过期/被撤销的 token 按「没带」处理，降级到匿名路径而不是 401。"""

    async def _fake_resolve(session, redis, *, token):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(auth_service, "resolve_token", _fake_resolve)

    result = await optional_authenticated_user_id(
        session=object(), redis=object(), authorization="Bearer expired"
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_failure_falls_back_to_anonymous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis/DB 异常不应让只读接口整体 500。"""

    async def _boom(session, redis, *, token):  # type: ignore[no-untyped-def]
        raise RuntimeError("redis down")

    monkeypatch.setattr(auth_service, "resolve_token", _boom)

    result = await optional_authenticated_user_id(
        session=object(), redis=object(), authorization="Bearer whatever"
    )
    assert result is None


# ── HTTP 层：验证接线确实生效，而不只是函数正确 ─────────────────────────


def test_endpoint_reads_token_owner_not_query_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """query 里写受害者 ID + 持有自己的 token → 实际查询的仍是 token 自己的身份。"""
    seen: list[str] = []

    async def _spy_list_rounds(session, external_user_id):  # type: ignore[no-untyped-def]
        seen.append(external_user_id)
        return []

    monkeypatch.setattr(conversation_route, "list_rounds", _spy_list_rounds)

    app = main_module.app
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[optional_authenticated_user_id] = lambda: "attacker-self"
    try:
        response = TestClient(app).get(
            "/v1/conversation/rounds", params={"external_user_id": "victim-id"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert seen == ["attacker-self"], "带 token 时必须忽略 query 里指向别人的 ID"


def test_endpoint_falls_back_to_query_param_when_anonymous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """匿名请求维持原行为，用请求里的 ID 查询。"""
    seen: list[str] = []

    async def _spy_list_rounds(session, external_user_id):  # type: ignore[no-untyped-def]
        seen.append(external_user_id)
        return []

    monkeypatch.setattr(conversation_route, "list_rounds", _spy_list_rounds)

    app = main_module.app
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[optional_authenticated_user_id] = lambda: None
    try:
        response = TestClient(app).get(
            "/v1/conversation/rounds", params={"external_user_id": "anon-123"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert seen == ["anon-123"]
