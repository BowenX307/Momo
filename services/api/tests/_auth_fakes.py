"""登录相关测试用的假 Redis / 假 Session。

不以 test_ 开头，pytest 不会当测试文件收集。

只实现 app.domain.auth.service 真正用到的那几个命令；行为要和真 Redis 一致的地方
（比如 get 不存在的 key 返回 None、pipeline 攒着最后一起执行）都对齐了，TTL 只记录
不实际过期——测试里不依赖时间流逝。
"""

# FakePipeline.set / FakeRedis 里的方法名会在类作用域里遮住内置的 set，
# 导致 `-> set[str]` 这类注解在类定义时求值失败。延迟求值绕开。
from __future__ import annotations

from uuid import uuid4

from app.infra.models import User


class FakePipeline:
    """攒操作，execute() 时一次性应用，模仿 redis-py 的 pipeline 语义。"""

    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def set(self, key, value, ex=None):  # type: ignore[no-untyped-def]
        self._ops.append(("set", key, value))
        return self

    def delete(self, key):  # type: ignore[no-untyped-def]
        self._ops.append(("delete", key))
        return self

    def incr(self, key):  # type: ignore[no-untyped-def]
        self._ops.append(("incr", key))
        return self

    def expire(self, key, ttl):  # type: ignore[no-untyped-def]
        self._ops.append(("expire", key, ttl))
        return self

    def sadd(self, key, value):  # type: ignore[no-untyped-def]
        self._ops.append(("sadd", key, value))
        return self

    def srem(self, key, value):  # type: ignore[no-untyped-def]
        self._ops.append(("srem", key, value))
        return self

    async def execute(self) -> None:
        for op in self._ops:
            name = op[0]
            if name == "set":
                self._redis.data[op[1]] = op[2]
            elif name == "delete":
                self._redis.data.pop(op[1], None)
                self._redis.sets.pop(op[1], None)
            elif name == "incr":
                self._redis.data[op[1]] = str(int(self._redis.data.get(op[1], 0)) + 1)
            elif name == "expire":
                self._redis.ttls[op[1]] = op[2]
            elif name == "sadd":
                self._redis.sets.setdefault(op[1], set()).add(op[2])
            elif name == "srem":
                members = self._redis.sets.get(op[1])
                if members is not None:
                    members.discard(op[2])
        self._ops.clear()


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = str(value)
        if ex is not None:
            self.ttls[key] = ex

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.sets.pop(key, None)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


class FakeSession:
    """只提供 service 层用到的三个方法；仓储层的查询走 monkeypatch，不碰真 SQL。"""

    def __init__(self, users: dict | None = None) -> None:
        # id -> User，供 session.get(User, uuid) 用
        self.users = users or {}
        self.commits = 0
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def get(self, model, pk):  # type: ignore[no-untyped-def]
        return self.users.get(pk)


def make_user(
    *,
    external_id: str = "anon-1",
    phone_number: str | None = "13800000000",
    password_hash: str | None = None,
) -> User:
    """构造一个不入库的 User；id 手动给，因为默认值要 flush 时才生成。"""
    return User(
        id=uuid4(),
        external_id=external_id,
        phone_number=phone_number,
        password_hash=password_hash,
        data_consent=False,
    )
