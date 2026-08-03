"""会话持久化接口，隔离领域编排与具体数据库实现。"""

from typing import Protocol
from uuid import UUID

from app.domain.safety import SafetyReason


class ConversationPersistence(Protocol):
    """保存一轮完整对话。"""

    async def save_exchange(
        self,
        *,
        external_user_id: str,
        conversation_id: UUID | None,
        persona: str,
        user_text: str,
        reply: str,
        safety_flag: SafetyReason,
        emotion: str,
        request_id: str,
        is_mock: bool,
        degraded: bool,
    ) -> UUID:
        """原子保存用户输入和助手回复，并返回实际会话 ID。"""
        ...
