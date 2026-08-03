"""TTS provider 抽象层。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """单次语音合成结果。"""

    audio: bytes
    content_type: str = "audio/mpeg"


class TTSError(RuntimeError):
    """TTS provider 调用失败时统一抛出。"""

    def __init__(
        self, code: str, message: str, upstream_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status


class TTSProvider(Protocol):
    """TTS provider 接口。"""

    async def synthesize(
        self,
        text: str,
        *,
        persona: str | None = None,
    ) -> SynthesisResult: ...


class MockTTSProvider:
    """无 key 时的 mock：返回空音频，前端可降级到浏览器 speechSynthesis。"""

    async def synthesize(
        self,
        text: str,
        *,
        persona: str | None = None,
    ) -> SynthesisResult:
        return SynthesisResult(audio=b"", content_type="audio/mpeg")
