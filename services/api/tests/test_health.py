"""健康检查中的数据库持久化状态测试。"""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import settings


client = TestClient(main_module.app)


def test_health_skips_database_when_persistence_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """关闭持久化时不探测数据库，并明确返回 null。"""
    monkeypatch.setattr(settings, "persistence_enabled", False)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["persistence_enabled"] is False
    assert body["database_connected"] is None


@pytest.mark.parametrize(
    ("connected", "expected_status"),
    [(True, "healthy"), (False, "degraded")],
)
def test_health_reports_database_connection(
    monkeypatch: pytest.MonkeyPatch,
    connected: bool,
    expected_status: str,
) -> None:
    """开启持久化时，把数据库探测结果反映到健康状态。"""

    async def fake_check_database_connection() -> bool:
        return connected

    monkeypatch.setattr(settings, "persistence_enabled", True)
    monkeypatch.setattr(
        main_module,
        "check_database_connection",
        fake_check_database_connection,
    )

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["persistence_enabled"] is True
    assert body["database_connected"] is connected
