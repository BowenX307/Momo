"""会话相关的 Pydantic schema。前后端共享语义在这里定义。

注意：枚举值要和未来 `packages/shared-types` 中的 TS union 字面量保持一致，
demo 阶段仅维护后端一份，前端按字符串字面量传入。
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.safety import SafetyReason


class Scene(str, Enum):
    """用户进入对话时选择的场景。

    与产品规则中的 5 个核心场景一一对应，命名采用英文 snake_case
    便于后端日志与前端枚举共享。
    """

    LATE_NIGHT = "late_night"
    RUMINATION = "rumination"
    RELATIONSHIP = "relationship"
    STRESS = "stress"
    LONELINESS = "loneliness"


class Persona(str, Enum):
    """AI 陪伴人格。

    - momo：温柔水母，稳定陪伴
    - iris：毒舌损友，高洞察力
    """

    MOMO = "momo"
    IRIS = "iris"


class HistoryMessage(BaseModel):
    """单条历史消息，角色为 user 或 assistant。"""

    role: Literal["user", "assistant"]
    content: str


class ChatDemoRequest(BaseModel):
    """单轮 demo 请求，支持传入历史上下文。

    scene 为 None 时由后端 LLM 自动分类；通常前端只在每个会话的**第一句**
    传 None，后续轮次把响应里返回的 scene 传回来，避免重复分类带来的延迟与成本。
    """

    user_text: str = Field(..., description="用户本轮输入；空字符串会走 safety 兜底")
    scene: Scene | None = Field(
        default=None,
        description="本轮场景；为 None 时后端用 SceneClassifier 自动分类",
    )
    persona: Persona = Field(
        default=Persona.MOMO,
        description="AI 人格选择；默认 momo，可切换为 iris",
    )
    history: list[HistoryMessage] = Field(
        default_factory=list,
        max_length=20,
        description="最近对话历史（最多 20 条 / 10 轮），不含本轮 user_text",
    )


class ChatDemoResponse(BaseModel):
    """单轮 demo 响应。

    - `reply` 永远有值，前端可直接渲染；
    - `audio_base64` 音频与文字一起返回，省去前端的第二次请求；
    - `safety_flag` 用于前端判断是否在 UI 上加"建议联系信任的人"等提示；
    - `is_mock` 在 demo 阶段透明化，方便现场区分回复来源。
    """

    reply: str
    scene: Scene
    safety_flag: SafetyReason
    is_mock: bool
    request_id: str
    degraded: bool = Field(
        default=False,
        description="true 表示原本走真模型但调用失败已降级到 Mock；前端可以加'临时离线'提示",
    )
    audio_base64: str = Field(default="", description="MP3 base64；空串时前端降级浏览器朗读")
    audio_content_type: str = Field(default="audio/mpeg")
    audio_is_mock: bool = Field(default=False)
