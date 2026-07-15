"""拍立得 Aftercare 的 Pydantic schema。

相机点击后调 `/v1/aftercare/generate`：后端读这次对话，选一个情绪档（决定正面照片），
并按当前人格口吻现写一句金句印在拍立得背面。
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.conversation.schemas import HistoryMessage, Persona

Mood = Literal["down", "anxious", "calm"]


class AftercareRequest(BaseModel):
    """生成拍立得所需的上下文。history 为空（还没聊）时后端直接落 calm 兜底。"""

    persona: Persona = Field(default=Persona.ROCKY, description="当前人格，决定金句口吻与署名")
    history: list[HistoryMessage] = Field(
        default_factory=list,
        max_length=20,
        description="最近对话历史（最多 20 条），据此判情绪 + 写金句",
    )


class AftercareResponse(BaseModel):
    """拍立得内容。mood 决定正面照片，quote 是背面手写金句（可含一个 \\n 换行）。"""

    mood: Mood = Field(description="down / anxious / calm，映射到 3 张 POV 自拍")
    quote: str = Field(description="背面金句，按人格口吻现写")
    is_mock: bool = Field(default=False, description="true 表示走了兜底金句，非模型现写")
