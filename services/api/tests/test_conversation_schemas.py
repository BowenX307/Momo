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
