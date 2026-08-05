"""主动选择和停用会话记忆摘要的测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.domain.conversation import memory_service

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CONVERSATION_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.mark.asyncio
async def test_disabling_memory_keeps_existing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = SimpleNamespace(
        id=CONVERSATION_ID,
        status="closed",
        include_in_memory=True,
    )
    memory = SimpleNamespace(status="ready", summary="保留的摘要")
    conversations = SimpleNamespace(get_for_user=AsyncMock(return_value=conversation))
    memories = SimpleNamespace(get_for_conversation=AsyncMock(return_value=memory))
    monkeypatch.setattr(
        memory_service,
        "ConversationRepository",
        lambda session: conversations,
    )
    monkeypatch.setattr(
        memory_service,
        "ConversationMemoryRepository",
        lambda session: memories,
    )
    session = SimpleNamespace(commit=AsyncMock())

    result = await memory_service.set_memory_selection(
        session,  # type: ignore[arg-type]
        USER_ID,
        CONVERSATION_ID,
        enabled=False,
    )

    assert conversation.include_in_memory is False
    assert memory.summary == "保留的摘要"
    assert result.memory_status == "ready"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_enabling_memory_generates_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated_at = datetime.now(UTC)
    conversation = SimpleNamespace(
        id=CONVERSATION_ID,
        status="closed",
        include_in_memory=False,
        updated_at=updated_at,
    )
    memory = SimpleNamespace(
        status="pending",
        summary="",
        model=None,
        prompt_version="v1",
        source_updated_at=None,
        generated_at=None,
    )
    conversations = SimpleNamespace(get_for_user=AsyncMock(return_value=conversation))
    memories = SimpleNamespace(
        get_for_conversation=AsyncMock(return_value=None),
        get_or_create=AsyncMock(return_value=memory),
    )
    messages = SimpleNamespace(
        list_all=AsyncMock(
            return_value=[
                SimpleNamespace(role="user", content="我最近在准备考试"),
                SimpleNamespace(role="assistant", content="先拆成小步骤。"),
            ]
        )
    )
    monkeypatch.setattr(
        memory_service,
        "ConversationRepository",
        lambda session: conversations,
    )
    monkeypatch.setattr(
        memory_service,
        "ConversationMemoryRepository",
        lambda session: memories,
    )
    monkeypatch.setattr(
        memory_service,
        "MessageRepository",
        lambda session: messages,
    )
    monkeypatch.setattr(
        memory_service,
        "_generate_summary",
        AsyncMock(return_value="用户正在准备考试，希望把任务拆小。"),
    )
    session = SimpleNamespace(commit=AsyncMock())

    result = await memory_service.set_memory_selection(
        session,  # type: ignore[arg-type]
        USER_ID,
        CONVERSATION_ID,
        enabled=True,
    )

    assert conversation.include_in_memory is True
    assert memory.status == "ready"
    assert memory.source_updated_at == updated_at
    assert result.memory_status == "ready"
    assert session.commit.await_count == 2
