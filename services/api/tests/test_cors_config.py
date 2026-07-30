"""CORS 白名单配置测试。

[2026-07-29] 原配置是 allow_origins=["*"] + allow_credentials=True，Starlette 在这个
组合下会回显调用方 Origin 而不是 "*"，等于给任意站点发带凭证的通行证。这里锁住收紧
后的行为，防止以后有人为了「本地调试方便」把 "*" 改回来。
"""

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
    """.env 里用逗号分隔而非 JSON 数组也要能解析，并去掉空格。"""
    settings = Settings(cors_origins="https://a.cn, https://b.cn")

    assert settings.cors_origins == ["https://a.cn", "https://b.cn"]


def test_cors_middleware_does_not_allow_credentials() -> None:
    """allow_credentials 必须关闭：登录走 Authorization 头，不依赖浏览器自动带凭证。"""
    cors = [m for m in app.user_middleware if "CORSMiddleware" in str(m)]
    assert cors, "CORS 中间件应当已注册"
    assert cors[0].kwargs["allow_credentials"] is False
