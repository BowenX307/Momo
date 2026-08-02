"""密码哈希与校验。

用 argon2（OWASP 当前推荐），哈希串自带盐和参数，不需要单独存盐。

⚠️ 两个函数都必须走线程池：argon2 默认 64MB 内存 / 3 轮迭代，单次 50~100ms 是**故意**
的（就是要让暴力破解变慢）。直接在 async 路由里同步调用会把事件循环卡住，那段时间整个
进程一条请求都处理不了。`run_in_threadpool` 由 starlette 提供，FastAPI 已经依赖它。
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
from starlette.concurrency import run_in_threadpool

_hasher = PasswordHasher()

# 手机号没注册、或注册了但没设密码时，仍然拿这个假哈希跑一次校验，让失败路径的耗时和
# 「密码输错」基本一致。否则响应快慢本身就泄露了「这个号存不存在」——登录接口会变成
# 手机号探测器。配合统一的 invalid_credentials 错误码一起用，缺一不可。
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-compare")


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    """校验密码；password_hash 为 None（没设过密码）时也会消耗等量时间后返回 False。"""
    target = password_hash or _DUMMY_HASH
    try:
        await run_in_threadpool(_hasher.verify, target, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    # 假哈希即便"验过了"也不算登录成功——只有真存在的哈希才作数。
    return password_hash is not None
