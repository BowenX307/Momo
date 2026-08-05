"""登录用户历史导入、删除和恢复策略测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.domain.conversation import history_service
from app.domain.conversation.schemas import ImportConversationRequest

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CONVERSATION_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.mark.asyncio
async def test_list_rounds_includes_memory_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    user = SimpleNamespace(id=USER_ID)
    conversation = SimpleNamespace(
        id=CONVERSATION_ID,
        persona="nini",
        mood=None,
        letter=None,
        status="closed",
        close_reason="user_end",
        include_in_memory=True,
        created_at=now,
        ended_at=now,
        deleted_at=None,
        purge_after=None,
    )
    users = SimpleNamespace(get_by_external_id=AsyncMock(return_value=user))
    conversations = SimpleNamespace(
        list_ended_for_user=AsyncMock(return_value=[conversation])
    )
    memories = SimpleNamespace(
        list_statuses=AsyncMock(return_value={CONVERSATION_ID: "ready"})
    )
    monkeypatch.setattr(history_service, "UserRepository", lambda session: users)
    monkeypatch.setattr(
        history_service,
        "ConversationRepository",
        lambda session: conversations,
    )
    monkeypatch.setattr(
        history_service,
        "ConversationMemoryRepository",
        lambda session: memories,
    )

    result = await history_service.list_rounds(
        SimpleNamespace(),  # type: ignore[arg-type]
        "external-user",
    )

    assert result[0].include_in_memory is True
    assert result[0].memory_status == "ready"
    memories.list_statuses.assert_awaited_once_with([CONVERSATION_ID])


@pytest.mark.asyncio
async def test_import_current_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = SimpleNamespace(id=CONVERSATION_ID)
    users = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id=USER_ID, data_consent=True))
    )
    conversations = SimpleNamespace(
        get_by_client_session=AsyncMock(return_value=existing)
    )
    messages = SimpleNamespace()
    monkeypatch.setattr(history_service, "UserRepository", lambda session: users)
    monkeypatch.setattr(
        history_service,
        "ConversationRepository",
        lambda session: conversations,
    )
    monkeypatch.setattr(history_service, "MessageRepository", lambda session: messages)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = await history_service.import_current_conversation(
        session,  # type: ignore[arg-type]
        USER_ID,
        ImportConversationRequest(
            client_session_id="browser-session",
            messages=[{"role": "user", "content": "你好"}],
        ),
    )

    assert result == CONVERSATION_ID
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_restore_preserves_target_and_trims_oldest_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=USER_ID)
    conversation = SimpleNamespace(
        id=CONVERSATION_ID,
        status="pending_delete",
        ended_at=datetime.now(UTC),
        persona="nini",
        scene=None,
        mood=None,
        letter=None,
        close_reason="user_end",
        include_in_memory=False,
        created_at=datetime.now(UTC),
        deleted_at=datetime.now(UTC),
        purge_after=datetime.now(UTC),
    )
    users = SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    conversations = SimpleNamespace(
        get_for_user=AsyncMock(return_value=conversation),
        restore=AsyncMock(),
        trim_for_user=AsyncMock(),
    )
    monkeypatch.setattr(history_service, "UserRepository", lambda session: users)
    monkeypatch.setattr(
        history_service,
        "ConversationRepository",
        lambda session: conversations,
    )
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    await history_service.restore_round(
        session,  # type: ignore[arg-type]
        USER_ID,
        CONVERSATION_ID,
    )

    conversations.restore.assert_awaited_once_with(conversation)
    conversations.trim_for_user.assert_awaited_once_with(
        USER_ID,
        keep=7,
        preserve_conversation_id=CONVERSATION_ID,
    )
    session.commit.assert_awaited_once()
