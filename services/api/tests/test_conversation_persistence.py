"""PostgreSQL 会话持久化策略测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.infra.conversation_persistence import PostgresConversationPersistence


@pytest.mark.asyncio
async def test_save_exchange_keeps_latest_seven_browser_conversations() -> None:
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    persistence = PostgresConversationPersistence(session)  # type: ignore[arg-type]
    user = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000001"))
    conversation = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        persona="nini",
    )

    persistence._users.get_or_create = AsyncMock(return_value=user)
    persistence._conversations.create = AsyncMock(return_value=conversation)
    persistence._conversations.trim_for_user = AsyncMock()
    persistence._messages.create = AsyncMock()

    result = await persistence.save_exchange(
        external_user_id="browser-user",
        conversation_id=None,
        persona="nini",
        user_text="今天有点累",
        reply="先休息一下。",
        safety_flag="ok",
        emotion="tired",
        request_id="request-1",
        is_mock=False,
        degraded=False,
    )

    assert result == conversation.id
    persistence._conversations.trim_for_user.assert_awaited_once_with(
        user.id,
        keep=7,
    )
    session.commit.assert_awaited_once()
