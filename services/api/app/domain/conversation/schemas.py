"""会话相关的 Pydantic schema。前后端共享语义在这里定义。

注意：枚举值要和未来 `packages/shared-types` 中的 TS union 字面量保持一致，
demo 阶段仅维护后端一份，前端按字符串字面量传入。
"""

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

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

    - youyou（优优）：毒舌损友，高洞察力
    - nini（妮妮）：白斗篷小精灵，知性直接，帮用户把问题变小
    """

    YOUYOU = "youyou"
    NINI = "nini"


class HistoryMessage(BaseModel):
    """单条历史消息，角色为 user 或 assistant。"""

    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class ChatDemoRequest(BaseModel):
    """单轮 demo 请求，支持传入历史上下文。

    scene 为 None 时由后端 LLM 自动分类；通常前端只在每个会话的**第一句**
    传 None，后续轮次把响应里返回的 scene 传回来，避免重复分类带来的延迟与成本。
    """

    user_text: str = Field(
        ...,
        max_length=2000,
        description="用户本轮输入（最多 2000 字符）；空字符串会走 safety 兜底",
    )
    external_user_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="前端生成的匿名用户标识；缺省时不持久化本轮对话",
    )
    conversation_id: UUID | None = Field(
        default=None,
        description="后端返回的会话 ID；第一轮为空，后续轮次原样传回",
    )
    scene: Scene | None = Field(
        default=None,
        description="本轮场景；为 None 时后端用 SceneClassifier 自动分类",
    )
    persona: Persona = Field(
        default=Persona.NINI,
        description="AI 人格选择；默认 nini（妮妮），可切换为 youyou（优优）",
    )
    history: list[HistoryMessage] = Field(
        default_factory=list,
        description="当前浏览器会话的对话历史，不含本轮 user_text",
    )

    @field_validator("scene", mode="before")
    @classmethod
    def _empty_scene_is_none(cls, v: object) -> object:
        """空串当作未指定。Unity 的 JsonUtility 会把 null 序列化成 ""，别让它吃 422。"""
        return None if v == "" else v

    @field_validator("conversation_id", mode="before")
    @classmethod
    def _empty_conversation_id_is_none(cls, v: object) -> object:
        """兼容把空会话 ID 序列化成空串的客户端。"""
        return None if v == "" else v


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
    conversation_id: UUID | None = Field(
        default=None,
        description="已持久化的会话 ID；未启用或写入失败时为空",
    )
    degraded: bool = Field(
        default=False,
        description="true 表示原本走真模型但调用失败已降级到 Mock；前端可以加'临时离线'提示",
    )
    audio_base64: str = Field(
        default="", description="MP3 base64；空串时前端降级浏览器朗读"
    )
    audio_content_type: str = Field(default="audio/mpeg")
    audio_is_mock: bool = Field(default=False)
    emotion: str = Field(default="", description="用户输入的情绪标签，空串表示未检测到")
    reaction: str = Field(
        default="",
        description=(
            "小人该播的反应动画，据于你这句回答判定；空串表示无（判定失败），"
            "前端回落 Idle。取值随人格：youyou=开心/伤心/疑惑/肯定/否定，nini=开心/伤心/疑惑/关心"
        ),
    )


class RoundSummary(BaseModel):
    """一个已结束归档的对话轮次，用于"查看历史轮次"列表。"""

    conversation_id: UUID
    persona: Persona
    scene: str | None = Field(default=None, description="该轮判定的场景，可能为空")
    mood: str | None = Field(default=None, description="结束时生成的拍立得情绪档")
    letter: str | None = Field(default=None, description="结束时生成的拍立得回信正文")
    created_at: str = Field(description="轮次开始时间，ISO 8601")
    ended_at: str = Field(description="轮次结束时间，ISO 8601")


class RoundMessage(BaseModel):
    """历史轮次里的一条消息（只读回看用）。"""

    role: Literal["user", "assistant"]
    content: str
    created_at: str = Field(description="ISO 8601")
