"""跨路由复用的登录用户依赖。"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.service import resolve_token_user
from app.infra.database import get_db_session
from app.infra.models import User
from app.infra.redis_client import get_redis


async def get_optional_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """没有 token 时返回游客；带了无效 token 时明确返回 401。"""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="invalid authorization header")
    user = await resolve_token_user(session, redis, token=token.strip())
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return user


async def require_current_user(
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> User:
    """要求已登录且完成首次数据授权。"""
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    if not user.data_consent:
        raise HTTPException(status_code=403, detail="data consent required")
    return user


OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]
CurrentUser = Annotated[User, Depends(require_current_user)]
