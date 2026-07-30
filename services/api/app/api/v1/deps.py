"""跨路由复用的依赖。

[2026-07-29] 新增 optional_authenticated_user_id：读 Authorization 头，带了有效 token
就返回 token 对应的 external_user_id，没带或 token 无效则返回 None。

为什么是「可选」而不是强制：本项目登录态与匿名态并存（见 58db4a0），匿名用户没有 token
但仍要能看自己的历史，所以不能一律 401。带了 token 的请求身份以 token 为准，匿名请求
维持原有的「信任请求里的 external_user_id」行为——登录用户因此得到保护，匿名用户的
可伪造问题仍在（需要产品侧决定是否强制登录，见 SECURITY-DEBT 笔记）。

token 无效/过期按「没带」处理而不是 401：过期只意味着回到未登录状态，降级到匿名路径是
原有行为、不构成功能回退；而攻击者省略请求头就能拿到同样的降级路径，所以 401 也换不来
额外的安全性。
"""

from typing import Annotated

import structlog
from fastapi import Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth import service as auth_service
from app.infra.database import get_db_session
from app.infra.redis_client import get_redis

logger = structlog.get_logger(__name__)


async def optional_authenticated_user_id(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """带有效 token 时返回其对应的 external_user_id，否则返回 None。"""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        resolved = await auth_service.resolve_token(session, redis, token=token)
    except Exception:
        # Redis / 数据库异常不应让只读接口整体挂掉，降级为匿名路径。
        logger.exception("optional_auth_resolve_failed")
        return None

    if resolved is None:
        logger.info("optional_auth_token_invalid")
        return None

    external_user_id, _phone_number = resolved
    return external_user_id


def resolve_owner_id(verified_user_id: str | None, claimed_user_id: str) -> str:
    """决定这次请求按谁的身份读数据。

    带 token 时以 token 为准：即便请求里的 external_user_id 指向别人，也只会读到
    token 自己的数据，冒名读取因此失效。不对不一致直接报错，是为了避免误伤——例如
    在另一个标签页登录后本标签页仍持有旧 id（前端会在登录后切换 id，见
    apps/web/app/yewne/chat/page.tsx，但多标签场景下仍可能短暂不一致）。
    """
    if verified_user_id is None:
        return claimed_user_id

    if verified_user_id != claimed_user_id:
        logger.warning(
            "owner_id_mismatch_token_wins",
            claimed=claimed_user_id,
            verified=verified_user_id,
        )
    return verified_user_id


OptionalAuthUserId = Annotated[str | None, Depends(optional_authenticated_user_id)]
