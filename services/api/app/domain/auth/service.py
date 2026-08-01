"""登录(手机号 + 验证码)编排逻辑：发码限流、校验、绑定老用户、签发/撤销 token。

Token 用服务端存储的随机字符串（Redis `auth_token:{token} -> user_id`，带 TTL），
不用 JWT——需要支持主动"退出登录"，opaque token 删一下 Redis 就失效，JWT 撤销
还得再搭一层黑名单，不如这样省事。
"""

import secrets
from datetime import date
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infra.models import User
from app.infra.repositories import UserRepository
from app.sms.provider import SmsError, SmsProvider

_CODE_KEY = "verify_code:{phone}"
_COOLDOWN_KEY = "verify_code_sent:{phone}"
_DAILY_KEY = "verify_code_daily:{phone}:{day}"
_TOKEN_KEY = "auth_token:{token}"
# [2026-08-01] 同一个验证码已经猜错几次，超过上限即作废。
_ATTEMPTS_KEY = "verify_code_attempts:{phone}"


class AuthError(Exception):
    """发码/校验失败时统一抛出，路由层据 code 映射成合适的 HTTP 状态。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _gen_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def send_code(
    redis: Redis,
    sms_provider: SmsProvider,
    *,
    phone_number: str,
) -> None:
    """限流校验通过后生成验证码、存 Redis、真正发短信。"""
    if await redis.get(_COOLDOWN_KEY.format(phone=phone_number)):
        raise AuthError("cooldown", "发送太频繁，请稍后再试")

    daily_key = _DAILY_KEY.format(phone=phone_number, day=date.today().isoformat())
    sent_today = int(await redis.get(daily_key) or 0)
    if sent_today >= settings.sms_daily_limit:
        raise AuthError("daily_limit", "今天这个手机号发送次数已达上限")

    code = _gen_code()
    try:
        await sms_provider.send_verification_code(phone_number, code)
    except SmsError as exc:
        raise AuthError("sms_failed", str(exc)) from exc

    await redis.set(
        _CODE_KEY.format(phone=phone_number), code, ex=settings.sms_code_ttl_seconds
    )
    await redis.set(
        _COOLDOWN_KEY.format(phone=phone_number),
        "1",
        ex=settings.sms_resend_cooldown_seconds,
    )
    pipe = redis.pipeline()
    pipe.incr(daily_key)
    pipe.expire(daily_key, 86400)
    await pipe.execute()


async def verify_code(
    session: AsyncSession,
    redis: Redis,
    *,
    phone_number: str,
    code: str,
    external_user_id: str,
) -> tuple[str, str, int]:
    """校验验证码，认老用户或绑定当前匿名用户，签发 token。

    返回 (token, 登录后应使用的 external_user_id, token 有效期秒数)。
    """
    code_key = _CODE_KEY.format(phone=phone_number)
    attempts_key = _ATTEMPTS_KEY.format(phone=phone_number)

    stored = await redis.get(code_key)
    if not stored or stored != code:
        # [2026-08-01] 原先猜错什么都不做：验证码是 6 位数字(100 万种)、有效期 5 分钟、
        # 这个接口又没有任何限流，等于可以无限次穷举。攻击者可以给别人的手机号发码再暴力
        # 破解，猜中即拿到合法 token，也就拿到那个人的全部对话记录。
        # 现在错够 verify_code_max_attempts 次就把验证码本身作废，逼他重新发送——而发送
        # 侧本来就有每日上限，于是每天的尝试次数从"无限"压到 10 × max_attempts。
        attempts = int(await redis.incr(attempts_key))
        if attempts == 1:
            # 跟验证码同寿命，验证码过期了计数也没有保留的意义。
            await redis.expire(attempts_key, settings.sms_code_ttl_seconds)

        if attempts >= settings.verify_code_max_attempts:
            await redis.delete(code_key)
            await redis.delete(attempts_key)
            raise AuthError("too_many_attempts", "错误次数过多，请重新获取验证码")

        raise AuthError("invalid_code", "验证码不对或已过期")

    await redis.delete(code_key)
    await redis.delete(attempts_key)

    users = UserRepository(session)
    existing = await users.get_by_phone_number(phone_number)
    if existing is not None:
        # 这个手机号已经绑过老用户：认那个老用户，历史消息延续。
        target = existing
    else:
        # 没绑过：把当前这个匿名用户直接绑上手机号。
        target = await users.get_or_create(external_user_id)
        target.phone_number = phone_number
        await session.flush()
    await session.commit()

    token = secrets.token_urlsafe(32)
    ttl_seconds = settings.auth_token_ttl_days * 86400
    await redis.set(_TOKEN_KEY.format(token=token), str(target.id), ex=ttl_seconds)

    return token, target.external_id, ttl_seconds


async def logout(redis: Redis, *, token: str) -> None:
    await redis.delete(_TOKEN_KEY.format(token=token))


async def resolve_token(
    session: AsyncSession, redis: Redis, *, token: str
) -> tuple[str, str | None] | None:
    """给 token 换回 (external_user_id, phone_number)；token 无效/过期返回 None。"""
    user_id_str = await redis.get(_TOKEN_KEY.format(token=token))
    if not user_id_str:
        return None
    user = await session.get(User, UUID(user_id_str))
    if user is None:
        return None
    return user.external_id, user.phone_number
