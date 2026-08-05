"""会话超时关闭与回收站到期清理。"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from app.core.config import settings
from app.infra.database import async_session_factory
from app.infra.repositories import ConversationRepository

logger = structlog.get_logger(__name__)


async def run_conversation_maintenance_once() -> tuple[int, int]:
    """执行一轮维护，返回（关闭数量，永久删除数量）。"""
    async with async_session_factory() as session:
        repository = ConversationRepository(session)
        cutoff = datetime.now(UTC) - timedelta(
            minutes=settings.conversation_idle_timeout_minutes
        )
        closed_ids = await repository.close_idle_before(cutoff)
        purged_ids = await repository.purge_due(datetime.now(UTC))
        await session.commit()
        return len(closed_ids), len(purged_ids)


async def conversation_maintenance_loop() -> None:
    """应用运行期间定期维护；所有操作均为幂等数据库更新。"""
    while True:
        await asyncio.sleep(settings.conversation_maintenance_interval_seconds)
        try:
            closed, purged = await run_conversation_maintenance_once()
            if closed or purged:
                logger.info(
                    "conversation_maintenance_completed",
                    closed=closed,
                    purged=purged,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("conversation_maintenance_failed")
