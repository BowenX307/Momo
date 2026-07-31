"""登录编排逻辑：发码限流、验证码/密码两条登录路径、协议同意落库、签发/撤销 token。

Token 用服务端存储的随机字符串（Redis `auth_token:{token} -> user_id`，带 TTL），
不用 JWT——需要支持主动"退出登录"，opaque token 删一下 Redis 就失效，JWT 撤销
还得再搭一层黑名单，不如这样省事。

[2026-07-30] 在原有的手机号+验证码之上补了两块：
- **密码登录**（可选的第二条路，不强制）：设过密码的用户可以跳过短信。老用户不受影响，
  password_hash 为空就只能继续走验证码。
- **协议同意**：两条登录路径都要求 agreed_to_terms，落到 users 表早就存在但一直没人写的
  data_consent / consent_version / consented_at 三个字段上。匿名用户不受影响（协议门槛
  只卡在注册/登录这一层，见 api/v1/deps.py 里对匿名态的说明）。
"""

import secrets
from datetime import date
from typing import Literal
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.auth.passwords import hash_password, verify_password
from app.infra.models import User
from app.infra.repositories import UserRepository
from app.sms.provider import SmsError, SmsProvider

logger = structlog.get_logger(__name__)

# 验证码按用途隔离：为登录发的码不能拿去重置密码（否则一次钓鱼拿到的码就能改密码）。
_CODE_KEY = "verify_code:{purpose}:{phone}"
# 冷却和每日上限**只按手机号**，不带 purpose——否则换个用途就能绕过限流。
_COOLDOWN_KEY = "verify_code_sent:{phone}"
_DAILY_KEY = "verify_code_daily:{phone}:{day}"
_TOKEN_KEY = "auth_token:{token}"
# token 反查索引：auth_token 那张表只能 token→user，没法按用户枚举他的所有 token。
# 重置密码后要把该用户其他设备全部踢下线，所以额外维护这个集合。
_USER_TOKENS_KEY = "user_tokens:{user_id}"
_LOGIN_FAIL_KEY = "login_fail:{phone}"

CodePurpose = Literal["login", "reset"]

# 用户同意的协议版本，对应 docs/于你Yewne_Alpha测试用户协议_Alpha1.0.docx。
# 协议改版时把这里和前端 apps/web/lib/legal/terms.ts 的 TERMS_VERSION 一起升，
# 老用户的 consent_version 对不上，就能筛出需要重新同意的人。
# 特意不放 config.py：那是服务器上的分叉文件，改它每次部署都要走 surgical 补丁。
TERMS_VERSION = "Alpha 1.0"

_MAX_LOGIN_FAILURES = 5
_LOGIN_LOCK_SECONDS = 15 * 60


class AuthError(Exception):
    """发码/校验失败时统一抛出，路由层据 code 映射成合适的 HTTP 状态。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _gen_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_phone(phone_number: str) -> str:
    """138****9307：日志里够用来定位是谁，又不落完整手机号。

    [2026-07-31] 加这个是因为一次真实事故查不动：7/29 有 6 条短信在运营商侧投递失败，
    我们的日志里 send-code 全是 200（阿里云"受理成功"≠"送达"），事后既不知道是哪些号码
    没收到，也没法拿去查 QuerySendDetails。留脱敏号码就能直接对上。
    """
    if len(phone_number) != 11:
        return "***"
    return f"{phone_number[:3]}****{phone_number[7:]}"


def _require_terms(agreed_to_terms: bool) -> None:
    """协议没勾就不往下走——不建用户、不校验密码、不签 token。"""
    if not agreed_to_terms:
        raise AuthError("terms_required", "需要先同意用户协议")


async def _issue_token(redis: Redis, user: User) -> tuple[str, int]:
    """签发 token 并登记到该用户的 token 集合里，返回 (token, 有效期秒数)。"""
    token = secrets.token_urlsafe(32)
    ttl_seconds = settings.auth_token_ttl_days * 86400
    user_tokens_key = _USER_TOKENS_KEY.format(user_id=user.id)

    pipe = redis.pipeline()
    pipe.set(_TOKEN_KEY.format(token=token), str(user.id), ex=ttl_seconds)
    pipe.sadd(user_tokens_key, token)
    # 集合本身也给个 TTL，免得用户再不登录就永远留在 Redis 里。
    pipe.expire(user_tokens_key, ttl_seconds)
    await pipe.execute()

    return token, ttl_seconds


async def _revoke_all_tokens(redis: Redis, user: User) -> None:
    """踢掉该用户所有设备的登录态（重置密码后调用）。

    集合里可能残留已经自然过期的 token，DEL 一个不存在的 key 不报错，忽略即可。
    """
    user_tokens_key = _USER_TOKENS_KEY.format(user_id=user.id)
    tokens = await redis.smembers(user_tokens_key)
    pipe = redis.pipeline()
    for token in tokens:
        pipe.delete(_TOKEN_KEY.format(token=token))
    pipe.delete(user_tokens_key)
    await pipe.execute()


async def _user_for_token(
    session: AsyncSession, redis: Redis, token: str
) -> User | None:
    """token → User；无效/过期/用户已删返回 None。

    Redis 客户端建的时候带了 decode_responses=True（见 infra/redis_client.py），拿到的
    一定是 str；stub 里声明成 bytes | str，所以显式转一次让类型检查过得去。
    """
    raw = await redis.get(_TOKEN_KEY.format(token=token))
    if not raw:
        return None
    return await session.get(User, UUID(str(raw)))


async def _consume_code(redis: Redis, *, phone_number: str, code: str, purpose: CodePurpose) -> None:
    """校验验证码并立即作废（用过一次就不能再用）。"""
    key = _CODE_KEY.format(purpose=purpose, phone=phone_number)
    stored = await redis.get(key)
    if not stored or stored != code:
        raise AuthError("invalid_code", "验证码不对或已过期")
    await redis.delete(key)


async def send_code(
    redis: Redis,
    sms_provider: SmsProvider,
    *,
    phone_number: str,
    purpose: CodePurpose = "login",
) -> None:
    """限流校验通过后生成验证码、存 Redis、真正发短信。"""
    masked = mask_phone(phone_number)

    if await redis.get(_COOLDOWN_KEY.format(phone=phone_number)):
        logger.info("sms_code_rejected", phone=masked, purpose=purpose, reason="cooldown")
        raise AuthError("cooldown", "发送太频繁，请稍后再试")

    daily_key = _DAILY_KEY.format(phone=phone_number, day=date.today().isoformat())
    sent_today = int(await redis.get(daily_key) or 0)
    if sent_today >= settings.sms_daily_limit:
        logger.info(
            "sms_code_rejected", phone=masked, purpose=purpose, reason="daily_limit"
        )
        raise AuthError("daily_limit", "今天这个手机号发送次数已达上限")

    code = _gen_code()
    try:
        await sms_provider.send_verification_code(phone_number, code)
    except SmsError as exc:
        logger.warning(
            "sms_code_send_failed", phone=masked, purpose=purpose, error=str(exc)
        )
        raise AuthError("sms_failed", str(exc)) from exc

    # ⚠️ "已受理"不等于"已送达"：运营商侧的投递失败是异步的，这里看不到。
    # 用户报告没收到时，拿这条日志里的脱敏号码去阿里云 QuerySendDetails 查真实送达状态。
    logger.info("sms_code_accepted", phone=masked, purpose=purpose)

    await redis.set(
        _CODE_KEY.format(purpose=purpose, phone=phone_number),
        code,
        ex=settings.sms_code_ttl_seconds,
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


async def _bind_or_get_user(
    session: AsyncSession, *, phone_number: str, external_user_id: str
) -> User:
    """认已绑定该手机号的老用户；没有就把当前这个匿名用户绑上去。"""
    users = UserRepository(session)
    existing = await users.get_by_phone_number(phone_number)
    if existing is not None:
        # 这个手机号已经绑过老用户：认那个老用户，历史消息延续。
        return existing
    # 没绑过：把当前这个匿名用户直接绑上手机号。
    target = await users.get_or_create(external_user_id)
    target.phone_number = phone_number
    await session.flush()
    return target


async def _record_consent(session: AsyncSession, user: User) -> None:
    """记下这次登录时用户同意的协议版本。"""
    await UserRepository(session).set_data_consent(
        user, granted=True, version=TERMS_VERSION
    )


async def verify_code(
    session: AsyncSession,
    redis: Redis,
    *,
    phone_number: str,
    code: str,
    external_user_id: str,
    agreed_to_terms: bool,
) -> tuple[str, str, int]:
    """校验验证码，认老用户或绑定当前匿名用户，签发 token。

    返回 (token, 登录后应使用的 external_user_id, token 有效期秒数)。
    """
    _require_terms(agreed_to_terms)
    await _consume_code(redis, phone_number=phone_number, code=code, purpose="login")

    target = await _bind_or_get_user(
        session, phone_number=phone_number, external_user_id=external_user_id
    )
    await _record_consent(session, target)
    await session.commit()

    token, ttl_seconds = await _issue_token(redis, target)
    # 和 sms_code_accepted 配对：发了码却没有这条，说明用户没走完（多半是没收到短信）。
    logger.info("login_succeeded", phone=mask_phone(phone_number), method="code")
    return token, target.external_id, ttl_seconds


async def login_with_password(
    session: AsyncSession,
    redis: Redis,
    *,
    phone_number: str,
    password: str,
    external_user_id: str,
    agreed_to_terms: bool,
) -> tuple[str, str, int]:
    """手机号 + 密码登录。返回值同 verify_code。

    两条反探测规则，改这个函数时务必保住：
    1. 手机号不存在、存在但没设密码、密码输错——三种情况**返回完全相同的错误码**。
    2. 三种情况都实际跑一次 argon2 校验（没密码时对假哈希跑），耗时不因账号是否存在而变。
    否则这个接口就成了「查某个手机号在不在库里」的工具。
    """
    _require_terms(agreed_to_terms)

    fail_key = _LOGIN_FAIL_KEY.format(phone=phone_number)
    failures = int(await redis.get(fail_key) or 0)
    if failures >= _MAX_LOGIN_FAILURES:
        raise AuthError("too_many_attempts", "密码错误次数过多，请稍后再试或用验证码登录")

    users = UserRepository(session)
    user = await users.get_by_phone_number(phone_number)
    # user 为 None 时照样进 verify（内部会拿假哈希跑），不能在这里提前 return。
    ok = await verify_password(user.password_hash if user else None, password)

    if not ok or user is None:
        pipe = redis.pipeline()
        pipe.incr(fail_key)
        pipe.expire(fail_key, _LOGIN_LOCK_SECONDS)
        await pipe.execute()
        raise AuthError("invalid_credentials", "手机号或密码不对")

    await redis.delete(fail_key)

    await _record_consent(session, user)
    await session.commit()

    token, ttl_seconds = await _issue_token(redis, user)
    logger.info("login_succeeded", phone=mask_phone(phone_number), method="password")
    return token, user.external_id, ttl_seconds


async def set_password(
    session: AsyncSession,
    redis: Redis,
    *,
    token: str,
    current_password: str | None,
    new_password: str,
) -> None:
    """已登录状态下设置或修改密码。

    已经有密码的必须验旧密码（防止别人趁人不备用未锁的页面改掉密码）；还没设过的直接设，
    因为持有有效 token 本身已经是身份证明。
    """
    user = await _user_for_token(session, redis, token)
    if user is None:
        raise AuthError("unauthorized", "登录状态已失效，请重新登录")

    if user.password_hash is not None:
        if not current_password:
            raise AuthError("invalid_credentials", "请填写当前密码")
        if not await verify_password(user.password_hash, current_password):
            raise AuthError("invalid_credentials", "当前密码不对")

    user.password_hash = await hash_password(new_password)
    await session.commit()


async def reset_password(
    session: AsyncSession,
    redis: Redis,
    *,
    phone_number: str,
    code: str,
    new_password: str,
    external_user_id: str,
    agreed_to_terms: bool,
) -> tuple[str, str, int]:
    """忘记密码：短信验证码验明身份 → 设新密码 → 踢掉旧会话 → 直接登录。

    返回值同 verify_code（重置完顺手把人登进去，省一步）。
    """
    _require_terms(agreed_to_terms)
    await _consume_code(redis, phone_number=phone_number, code=code, purpose="reset")

    target = await _bind_or_get_user(
        session, phone_number=phone_number, external_user_id=external_user_id
    )
    target.password_hash = await hash_password(new_password)
    await _record_consent(session, target)
    await session.commit()

    # 密码换了，其他设备上的登录态一律作废——这是重置密码的意义之一。
    await _revoke_all_tokens(redis, target)
    # 失败计数也清掉，否则刚重置完还被之前的失败次数锁着。
    await redis.delete(_LOGIN_FAIL_KEY.format(phone=phone_number))

    token, ttl_seconds = await _issue_token(redis, target)
    return token, target.external_id, ttl_seconds


async def logout(redis: Redis, *, token: str) -> None:
    user_id_str = await redis.get(_TOKEN_KEY.format(token=token))
    pipe = redis.pipeline()
    pipe.delete(_TOKEN_KEY.format(token=token))
    if user_id_str:
        pipe.srem(_USER_TOKENS_KEY.format(user_id=user_id_str), token)
    await pipe.execute()


async def resolve_token(
    session: AsyncSession, redis: Redis, *, token: str
) -> tuple[str, str | None] | None:
    """给 token 换回 (external_user_id, phone_number)；token 无效/过期返回 None。"""
    user = await _user_for_token(session, redis, token)
    if user is None:
        return None
    return user.external_id, user.phone_number


async def resolve_token_user(
    session: AsyncSession, redis: Redis, *, token: str
) -> User | None:
    """同 resolve_token，但返回整个 User（/me 要读 password_hash 判断有没有设过密码）。"""
    return await _user_for_token(session, redis, token)
