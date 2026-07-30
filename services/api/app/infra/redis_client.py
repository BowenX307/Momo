"""Redis 连接管理——验证码和登录 token 存这里。"""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import settings

redis_pool: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """为每次请求提供共享的 Redis 客户端（连接池内部复用，不用每次新建）。"""
    yield redis_pool
