"""STT provider 抽象层。

所有语音转写业务只依赖 `STTProvider` Protocol；具体 provider（Whisper、Mock 等）
在 `app/stt/factory.py` 里按运行时配置选出。

`MockSTTProvider` 用于本地开发与无 key 时的 demo 兜底。
`STTError` 是 provider 层向编排层抛出的统一错误信号。
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """单次转写结果。"""

    text: str
    language: str = "zh"


class STTError(RuntimeError):
    """STT provider 调用失败时统一抛出。"""

    def __init__(
        self, code: str, message: str, upstream_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status


class STTProvider(Protocol):
    """STT provider 接口。"""

    async def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> TranscriptionResult: ...


_MOCK_SAMPLES: tuple[str, ...] = (
    "今晚有点睡不着，脑子里一直在想今天的事。",
    "跟他吵完架之后，心里还是堵得慌。",
    "最近压力太大了，感觉快要撑不住了。",
    "就是突然不想一个人待着了。",
)


class MockSTTProvider:
    """固定样本的 mock STT，用于 demo 与离线开发。"""

    async def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> TranscriptionResult:
        if len(audio) < 100:
            return TranscriptionResult(text="")
        # 按音频长度挑一条样本，便于肉眼区分不同录音
        sample = _MOCK_SAMPLES[len(audio) % len(_MOCK_SAMPLES)]
        return TranscriptionResult(text=sample)
