"""给少年梓辛渲染不同 pitch,挑一个不低沉的。
运行:uv run python _probe_iris_pitch.py → voice_samples/_pitch_*.mp3
"""

import asyncio
import base64
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("DOUBAO_TTS_API_KEY", "")
ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
SPEAKER = "zh_male_shaonianzixin_moon_bigtts"
RESOURCE = "seed-tts-1.0"
RATE = 18
TEXT = "我知道你不是真的想睡,你只是不想面对明天。行吧,那就再赖一会儿,但别骗自己说这是休息。"

OUT = Path("voice_samples")
PITCHES = [0, 2, 4, 6]  # 当前是 -2(低沉),往上抬


async def one(pitch: int) -> None:
    payload = {
        "user": {"uid": "probe"},
        "req_params": {
            "text": TEXT,
            "speaker": SPEAKER,
            "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": RATE},
            "additions": json.dumps({
                "post_process": {"pitch": float(pitch)},
                "disable_markdown_filter": True,
            }),
        },
    }
    headers = {"X-Api-Key": API_KEY, "X-Api-Resource-Id": RESOURCE, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(ENDPOINT, headers=headers, json=payload)
    chunks = []
    for line in r.content.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("data"):
            chunks.append(base64.b64decode(obj["data"]))
    if chunks:
        p = OUT / f"_pitch_{pitch:+d}.mp3"
        p.write_bytes(b"".join(chunks))
        print(f"  ✓ pitch={pitch:+d} → {p.name}")
    else:
        print(f"  ✗ pitch={pitch:+d} 空音频 {r.status_code}")


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    for p in PITCHES:
        await one(p)


if __name__ == "__main__":
    asyncio.run(main())
