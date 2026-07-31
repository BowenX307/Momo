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


# [2026-08-01] 下面三个用例必须经由 monkeypatch.setenv 走真正的环境变量来源。
# 之前写成 Settings(cors_origins="a,b") 直接传构造函数，绕过了 EnvSettingsSource，
# 于是测试是绿的、而真配进 .env 时服务启动即 SettingsError（pydantic-settings 会在
# 模型校验前先把 list 类型的环境变量按 JSON 预解析）。构造函数那条路测不出这个。
def test_cors_origins_accepts_comma_separated_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """.env 里用逗号分隔而非 JSON 数组也要能解析，并去掉空格。"""
    monkeypatch.setenv("CORS_ORIGINS", "https://a.cn, https://b.cn")

    assert Settings().cors_origins == ["https://a.cn", "https://b.cn"]


def test_cors_origins_still_accepts_json_array_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已经按 JSON 数组配好的环境不应因为这次改动而失效。"""
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.cn", "https://b.cn"]')

    assert Settings().cors_origins == ["https://a.cn", "https://b.cn"]


def test_cors_origins_single_value_env_needs_no_comma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只配一个域名时不必写逗号，也不该被当成 JSON 解析失败。"""
    monkeypatch.setenv("CORS_ORIGINS", "https://only.cn")

    assert Settings().cors_origins == ["https://only.cn"]


def test_cors_middleware_does_not_allow_credentials() -> None:
    """allow_credentials 必须关闭：登录走 Authorization 头，不依赖浏览器自动带凭证。"""
    cors = [m for m in app.user_middleware if "CORSMiddleware" in str(m)]
    assert cors, "CORS 中间件应当已注册"
    assert cors[0].kwargs["allow_credentials"] is False
