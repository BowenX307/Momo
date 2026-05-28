"""语音相关的 Pydantic schema。"""

from app.domain.conversation.schemas import Scene
from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    """POST /v1/speech/transcribe 响应。"""

    text: str = Field(..., description="转写后的用户文本；空串表示未识别到有效语音")
    language: str = Field(default="zh", description="识别语言")
    is_mock: bool = Field(..., description="true 表示走 MockSTT，便于 demo 区分来源")
    request_id: str


class SynthesizeRequest(BaseModel):
    """POST /v1/speech/synthesize 请求。"""

    text: str = Field(
        ..., min_length=1, max_length=2000, description="要合成的 MOMO 回复文本"
    )
    scene: Scene | None = Field(
        default=None,
        description="可选场景，用于微调语速等 TTS 参数",
    )


class SynthesizeResponse(BaseModel):
    """POST /v1/speech/synthesize 响应。"""

    audio_base64: str = Field(
        ...,
        description="MP3 音频 base64；空串表示 mock 或未生成，前端可降级浏览器朗读",
    )
    content_type: str = Field(default="audio/mpeg")
    is_mock: bool
    request_id: str
