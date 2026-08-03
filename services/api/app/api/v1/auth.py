"""手机号登录相关路由。

- POST /v1/auth/send-code       发验证码（purpose 区分登录 / 重置密码）
- POST /v1/auth/verify-code     验证码登录
- POST /v1/auth/login-password  密码登录
- POST /v1/auth/set-password    已登录状态下设置或修改密码
- POST /v1/auth/reset-password  忘记密码：验证码验身份后重设并直接登录
- POST /v1/auth/logout          退出
- GET  /v1/auth/me              当前登录态

编排逻辑在 `app.domain.auth.service` 里；各类失败统一抛 `AuthError`，
这里按 code 映射成对应的 HTTP 状态。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import enforce_rate_limit
from app.core.config import settings
from app.domain.auth import service
from app.domain.auth.schemas import (
    LogoutRequest,
    MeResponse,
    PasswordLoginRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    SendCodeResponse,
    SetPasswordRequest,
    VerifyCodeRequest,
    VerifyCodeResponse,
)
from app.infra.database import get_db_session
from app.infra.redis_client import get_redis
from app.sms.factory import get_sms_provider

router = APIRouter(prefix="/auth", tags=["auth"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

_ERROR_STATUS = {
    "cooldown": 429,
    "daily_limit": 429,
    # [2026-08-01] too_many_attempts 现在有两个来源：密码连续错太多，以及验证码猜错超限。
    "too_many_attempts": 429,
    "invalid_code": 400,
    "terms_required": 400,
    "weak_password": 400,
    "invalid_credentials": 401,
    "unauthorized": 401,
    "sms_failed": 502,
}


def _http_error(exc: service.AuthError) -> HTTPException:
    return HTTPException(
        status_code=_ERROR_STATUS.get(exc.code, 400),
        detail={"code": exc.code, "message": str(exc)},
    )


def _bearer_token(authorization: str | None) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    return token


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(request: SendCodeRequest, redis: RedisDep) -> SendCodeResponse:
    sms_provider, _ = get_sms_provider()
    try:
        await service.send_code(
            redis,
            sms_provider,
            phone_number=request.phone_number,
            purpose=request.purpose,
        )
    except service.AuthError as exc:
        raise _http_error(exc) from exc
    return SendCodeResponse()


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code_route(
    request: VerifyCodeRequest,
    session: DatabaseSession,
    redis: RedisDep,
    http_request: Request,
) -> VerifyCodeResponse:
    # [2026-08-01] 按手机号限流。配合 service 里的猜错次数上限一起挡暴力破解：
    # 次数上限压住单个验证码能被试几次，这里压住单位时间能发起多少次尝试。
    await enforce_rate_limit(
        http_request,
        redis,
        bucket="verify_code",
        limit=settings.rate_limit_verify_code_per_minute,
        identity=request.phone_number,
    )
    try:
        token, external_user_id, ttl_seconds = await service.verify_code(
            session,
            redis,
            phone_number=request.phone_number,
            code=request.code,
            external_user_id=request.external_user_id,
            agreed_to_terms=request.agreed_to_terms,
        )
    except service.AuthError as exc:
        raise _http_error(exc) from exc
    return VerifyCodeResponse(
        token=token, external_user_id=external_user_id, expires_in_seconds=ttl_seconds
    )


@router.post("/login-password", response_model=VerifyCodeResponse)
async def login_password_route(
    request: PasswordLoginRequest,
    session: DatabaseSession,
    redis: RedisDep,
) -> VerifyCodeResponse:
    try:
        token, external_user_id, ttl_seconds = await service.login_with_password(
            session,
            redis,
            phone_number=request.phone_number,
            password=request.password,
            external_user_id=request.external_user_id,
            agreed_to_terms=request.agreed_to_terms,
        )
    except service.AuthError as exc:
        raise _http_error(exc) from exc
    return VerifyCodeResponse(
        token=token, external_user_id=external_user_id, expires_in_seconds=ttl_seconds
    )


@router.post("/set-password", status_code=204)
async def set_password_route(
    request: SetPasswordRequest,
    session: DatabaseSession,
    redis: RedisDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    try:
        await service.set_password(
            session,
            redis,
            token=_bearer_token(authorization),
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except service.AuthError as exc:
        raise _http_error(exc) from exc


@router.post("/reset-password", response_model=VerifyCodeResponse)
async def reset_password_route(
    request: ResetPasswordRequest,
    session: DatabaseSession,
    redis: RedisDep,
) -> VerifyCodeResponse:
    try:
        token, external_user_id, ttl_seconds = await service.reset_password(
            session,
            redis,
            phone_number=request.phone_number,
            code=request.code,
            new_password=request.new_password,
            external_user_id=request.external_user_id,
            agreed_to_terms=request.agreed_to_terms,
        )
    except service.AuthError as exc:
        raise _http_error(exc) from exc
    return VerifyCodeResponse(
        token=token, external_user_id=external_user_id, expires_in_seconds=ttl_seconds
    )


@router.post("/logout", status_code=204)
async def logout_route(request: LogoutRequest, redis: RedisDep) -> None:
    await service.logout(redis, token=request.token)


@router.get("/me", response_model=MeResponse)
async def me_route(
    session: DatabaseSession,
    redis: RedisDep,
    authorization: Annotated[str | None, Header()] = None,
) -> MeResponse:
    user = await service.resolve_token_user(
        session, redis, token=_bearer_token(authorization)
    )
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return MeResponse(
        external_user_id=user.external_id,
        phone_number=user.phone_number,
        has_password=user.password_hash is not None,
        consent_version=user.consent_version,
    )
