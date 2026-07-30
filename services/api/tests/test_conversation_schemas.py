"""聊天请求的历史与单条消息长度限制测试。"""

import pytest
from pydantic import ValidationError

from app.domain.conversation.schemas import ChatDemoRequest, HistoryMessage


def test_chat_history_is_not_limited_to_seven_question_answer_pairs() -> None:
    history = [
        HistoryMessage(
            role="user" if index % 2 == 0 else "assistant",
            content="test",
        )
        for index in range(20)
    ]

    request = ChatDemoRequest(user_text="继续聊", history=history)

    assert len(request.history) == 20


def test_history_message_rejects_more_than_2000_characters() -> None:
    with pytest.raises(ValidationError):
        HistoryMessage(role="user", content="x" * 2001)


def test_user_text_rejects_more_than_2000_characters() -> None:
    with pytest.raises(ValidationError):
        ChatDemoRequest(user_text="x" * 2001)


# [2026-07-29] 以下两个用例覆盖新加的 history 条数上限（200 条）。
def test_history_accepts_up_to_200_messages() -> None:
    """200 条是上限本身，必须放行——正常长会话不应被误伤。"""
    history = [HistoryMessage(role="user", content="嗯") for _ in range(200)]

    request = ChatDemoRequest(user_text="继续聊", history=history)

    assert len(request.history) == 200


def test_history_rejects_more_than_200_messages() -> None:
    """条数无上限时，一个请求可以塞进上千条历史并被全额计费。"""
    history = [HistoryMessage(role="user", content="嗯") for _ in range(201)]

    with pytest.raises(ValidationError):
        ChatDemoRequest(user_text="继续聊", history=history)
