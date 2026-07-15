"""临时:走真实 DoubaoTTSProvider.synthesize(persona=...) 验证 iris 换音色。
运行:uv run python _iris_voice_check.py  → voice_samples/ 里生成 mp3 双击试听。
"""

import asyncio
from pathlib import Path

from app.tts.doubao import DoubaoTTSProvider, _PERSONA_VOICE_OVERRIDES, _DEFAULT_RATE
from app.core.config import settings

# iris 典型台词:高洞察·有点毒嘴,能暴露音色是否"知性有距离感"
TEXT = "我知道你不是真的想睡,你只是不想面对明天。行吧,那就再赖一会儿,但别骗自己说这是休息。"

OUT = Path("voice_samples")


async def one(persona: str) -> None:
    ov = _PERSONA_VOICE_OVERRIDES.get(persona, {})
    voice = ov.get("speaker", settings.doubao_tts_voice)
    rate = ov.get("speech_rate", _DEFAULT_RATE)
    print(f"→ persona={persona}  speaker={voice}  rate={rate}")
    res = await DoubaoTTSProvider().synthesize(TEXT, scene="loneliness", persona=persona)
    if not res.audio:
        print(f"  ✗ {persona}: 空音频")
        return
    p = OUT / f"_check_{persona}.mp3"
    p.write_bytes(res.audio)
    print(f"  ✓ {p}  ({len(res.audio)} bytes)")


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    await one("iris")   # 应走灿灿
    await one("rocky")  # 对照:走全局小何


if __name__ == "__main__":
    asyncio.run(main())
