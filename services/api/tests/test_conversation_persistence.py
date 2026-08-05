"""PostgreSQL 会话持久化策略测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.infra.conversation_persistence import PostgresConversationPersistence


@pytest.mark.asyncio
async def test_save_exchange_keeps_latest_seven_browser_conversations() -> None:
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    user = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000001"))
    persistence = PostgresConversationPersistence(  # type: ignore[arg-type]
        session,
        user_id=user.id,
    )
    conversation = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        persona="nini",
        status="active",
    )

    user.data_consent = True
    persistence._users.get_by_id = AsyncMock(return_value=user)
    persistence._conversations.create = AsyncMock(return_value=conversation)
    persistence._conversations.trim_for_user = AsyncMock()
    persistence._messages.create = AsyncMock()

    result = await persistence.save_exchange(
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
        preserve_conversation_id=conversation.id,
    )
    session.commit.assert_awaited_once()
