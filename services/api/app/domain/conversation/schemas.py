"""会话相关的 Pydantic schema。前后端共享语义在这里定义。

注意：枚举值要和未来 `packages/shared-types` 中的 TS union 字面量保持一致，
demo 阶段仅维护后端一份，前端按字符串字面量传入。
"""

from enum import Enum

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


class ChatDemoRequest(BaseModel):
    """单轮 demo 请求。下周五 demo 刻意不做多轮上下文。"""

    user_text: str = Field(..., description="用户本轮输入；空字符串会走 safety 兜底")
    scene: Scene = Field(default=Scene.LONELINESS, description="本轮所处场景")


class ChatDemoResponse(BaseModel):
    """单轮 demo 响应。

    - `reply` 永远有值，前端可直接渲染；
    - `safety_flag` 用于前端判断是否在 UI 上加"建议联系信任的人"等提示；
    - `is_mock` 在 demo 阶段透明化，方便现场区分回复来源。
    """

    reply: str
    scene: Scene
    safety_flag: SafetyReason
    is_mock: bool
    request_id: str
