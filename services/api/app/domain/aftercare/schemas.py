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

    persona: Persona = Field(default=Persona.NINI, description="当前人格，决定金句口吻与署名")
    history: list[HistoryMessage] = Field(
        default_factory=list,
        max_length=20,
        description="最近对话历史（最多 20 条），据此判情绪 + 写金句",
    )


class AftercareResponse(BaseModel):
    """拍立得内容。mood 决定正面照片，letter 是背面的回信正文（≤100 字，可含 \\n 分段）。"""

    mood: Mood = Field(description="down / anxious / calm，由场景映射，决定 3 张 POV 自拍选哪张")
    quote: str = Field(description="已废弃，内容与 letter 相同；留作旧前端兼容")
    letter: str = Field(default="", description="回信正文（12 场景回信小精灵产出，≤100 字）")
    scene: str = Field(
        default="",
        description="判定的场景键（blank_entry…withdrawal / safety_override），空串=判定失败",
    )
    is_mock: bool = Field(default=False, description="true 表示走了兜底回信，非模型现写")
