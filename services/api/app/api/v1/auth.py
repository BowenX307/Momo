"""POST /v1/auth/send-code、/verify-code、/logout，GET /v1/auth/me —— 手机号登录。

编排逻辑在 `app.domain.auth.service` 里；发码限流失败/校验失败统一抛
`AuthError`，这里按 code 映射成对应的 HTTP 状态。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth import service
from app.domain.auth.schemas import (
    LogoutRequest,
    MeResponse,
    SendCodeRequest,
    SendCodeResponse,
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
    "invalid_code": 400,
    "sms_failed": 502,
}


def _http_error(exc: service.AuthError) -> HTTPException:
    return HTTPException(
        status_code=_ERROR_STATUS.get(exc.code, 400),
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(request: SendCodeRequest, redis: RedisDep) -> SendCodeResponse:
    sms_provider, _ = get_sms_provider()
    try:
        await service.send_code(
            redis, sms_provider, phone_number=request.phone_number
        )
    except service.AuthError as exc:
        raise _http_error(exc) from exc
    return SendCodeResponse()


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code_route(
    request: VerifyCodeRequest,
    session: DatabaseSession,
    redis: RedisDep,
) -> VerifyCodeResponse:
    try:
        token, external_user_id, ttl_seconds = await service.verify_code(
            session,
            redis,
            phone_number=request.phone_number,
            code=request.code,
            external_user_id=request.external_user_id,
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
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    resolved = await service.resolve_token(session, redis, token=token)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    external_user_id, phone_number = resolved
    return MeResponse(external_user_id=external_user_id, phone_number=phone_number)
