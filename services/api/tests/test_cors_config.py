"""CORS 白名单配置测试。

[2026-07-29] 原配置是 allow_origins=["*"] + allow_credentials=True，Starlette 在这个
组合下会回显调用方 Origin 而不是 "*"，等于给任意站点发带凭证的通行证。这里锁住收紧
后的行为，防止以后有人为了「本地调试方便」把 "*" 改回来。
"""

import pytest

from app.core.config import Settings
from app.main import app


def test_cors_defaults_do_not_allow_all_origins() -> None:
    """默认白名单里不能出现通配符。"""
    assert "*" not in Settings().cors_origins


def test_cors_defaults_cover_production_and_local_dev() -> None:
    """线上两个域名 + 本地开发两个地址都要在白名单里。"""
    origins = Settings().cors_origins

    assert "https://uniai.net.cn" in origins
    assert "https://www.uniai.net.cn" in origins
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_cors_origins_accepts_comma_separated_env_value() -> None:
    """.env 里用逗号分隔而非 JSON 数组也要能解析，并去掉空格。

    ⚠️ 这条走的是 init 参数，不经过环境变量源；真正的 env 路径见下面两条——
    2026-07-31 之前只有这一条，结果 env 路径其实是坏的却一直绿着。
    """
    settings = Settings(cors_origins="https://a.cn, https://b.cn")

    assert settings.cors_origins == ["https://a.cn", "https://b.cn"]


def test_cors_origins_comma_separated_from_real_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[2026-07-31] 从真实环境变量读逗号分隔值。

    没有 NoDecode 时，pydantic-settings 会先对 list 字段做 json.loads，在 mode="before"
    校验器之前就抛 SettingsError，服务起不来——照 config.py 注释配 .env 就是生产事故。
    """
    monkeypatch.setenv("CORS_ORIGINS", "https://a.cn, https://b.cn")

    assert Settings().cors_origins == ["https://a.cn", "https://b.cn"]


def test_cors_origins_json_array_from_real_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON 数组写法要继续可用——已经按这个格式配好的 .env 不能被这次修复弄坏。"""
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.cn", "https://b.cn"]')

    assert Settings().cors_origins == ["https://a.cn", "https://b.cn"]


def test_cors_middleware_does_not_allow_credentials() -> None:
    """allow_credentials 必须关闭：登录走 Authorization 头，不依赖浏览器自动带凭证。"""
    cors = [m for m in app.user_middleware if "CORSMiddleware" in str(m)]
    assert cors, "CORS 中间件应当已注册"
    assert cors[0].kwargs["allow_credentials"] is False
