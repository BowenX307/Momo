"""[2026-08-01] 基于 Redis 的固定窗口限流。

用固定窗口(INCR + EXPIRE)而不是滑动窗口:实现只有几行、不依赖 Lua 脚本,代价是窗口
边界处最多可能放过两倍额度(窗口末尾打满 + 新窗口开头再打满)。对"防刷爆账单/防暴力
破解"这个目的够用;真要精确到每秒再换滑动窗口。

Redis 不可用时**放行**并记日志。限流是保护措施,不该因为它自己挂了就让聊天整体不可用
——对一个情绪陪伴产品来说,用户正难受时打不开比多花点钱严重得多。
"""

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


async def allow(
    redis: Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """在窗口内累加一次；未超额度返回 True。异常一律放行。"""
    if limit <= 0:
        return True

    try:
        count = int(await redis.incr(key))

        # 只在窗口第一次计数时设过期,不能每次都刷新——每次刷新会让持续打请求的人
        # 把窗口无限延长,反而永远解不了封。
        if count == 1:
            await redis.expire(key, window_seconds)
        elif int(await redis.ttl(key)) < 0:
            # 兜底:上一次 expire 没设上(比如进程在 incr 和 expire 之间挂了),
            # 否则这个 key 会永久存在,把用户永久挡在外面。
            await redis.expire(key, window_seconds)
    except Exception:
        logger.warning("rate_limit_backend_unavailable", key=key)
        return True

    return count <= limit
