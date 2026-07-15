"""探测轻快男声/少年音候选:每个 voice 依次试 seed-tts-2.0 / 1.0,能出声就存 mp3。
运行:uv run python _probe_male_voices.py  → voice_samples/_male_*.mp3 双击试听。
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

# iris 毒嘴台词——听音色是否"轻快/少年/不成熟"
TEXT = "我知道你不是真的想睡,你只是不想面对明天。行吧,那就再赖一会儿,但别骗自己说这是休息。"

# (label, voice_id)  —— 偏年轻/清爽/少年的男声候选
CANDIDATES = [
    ("xiaotian_小天",      "zh_male_taocheng_uranus_bigtts"),
    ("shaonian_少年梓辛",  "zh_male_shaonianzixin_moon_bigtts"),
    ("yangguang_阳光青年", "zh_male_yangguangqingnian_moon_bigtts"),
    ("qingshuang_清爽男大","zh_male_qingshuangnanda_mars_bigtts"),
    ("yunzhou_云舟_对照",  "zh_male_m191_uranus_bigtts"),
]
RESOURCES = ["seed-tts-2.0", "seed-tts-1.0"]

OUT = Path("voice_samples")


async def probe(label: str, voice: str) -> None:
    payload = {
        "user": {"uid": "probe"},
        "req_params": {
            "text": TEXT,
            "speaker": voice,
            "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": -6},
            "additions": json.dumps({"disable_markdown_filter": True}),
        },
    }
    for res in RESOURCES:
        headers = {"X-Api-Key": API_KEY, "X-Api-Resource-Id": res, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(ENDPOINT, headers=headers, json=payload)
        except Exception as e:
            print(f"  {label} [{res}] 网络错误 {e}")
            continue
        if r.status_code != 200:
            print(f"  {label} [{res}] HTTP {r.status_code} {r.text[:120]}")
            continue
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
            p = OUT / f"_male_{label}.mp3"
            p.write_bytes(b"".join(chunks))
            print(f"  ✓ {label}  speaker={voice}  resource={res}  → {p.name}")
            return
        print(f"  {label} [{res}] 空音频")
    print(f"  ✗ {label} 两个 resource 都失败")


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    for label, voice in CANDIDATES:
        await probe(label, voice)


if __name__ == "__main__":
    asyncio.run(main())
