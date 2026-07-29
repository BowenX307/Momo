"""探测"萌/可爱"风格候选声线——2026-07-28 产品需求:优优/妮妮各换一个更萌可爱的声线。

运行:uv run python _probe_cute_voices.py  → voice_samples/_cute_*.mp3 双击试听。

背景:之前两批(男声/女声)候选都偏"熟人感/毒舌/知性"方向,没特意找过"萌"向的。
这批专门挑官方音色表里标"萌/可爱/甜"关键词的候选，同时用两句不同风格的台词
（优优毒舌 + 妮妮温柔）各录一遍，方便直接对着人格判断合不合适。
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

TEXTS = {
    "youyou": "我知道你不是真的想睡,你只是不想面对明天。行吧,那就再赖一会儿,但别骗自己说这是休息。",
    "nini": "嗯,我在呢。不管今天发生了什么,你都可以跟我说。有时候把心里压着的东西说出来,会好受一点的。",
}

# (label, voice_id, resource_id 候选顺序) —— 官方音色表里标"萌/可爱/甜"关键词的候选
CANDIDATES = [
    ("mengyatou_萌丫头",       "zh_female_mengyatou_mars_bigtts",      ["seed-tts-2.0", "seed-tts-1.0"]),
    ("tianmeixiaoyuan_甜美小源", "zh_female_tianmeixiaoyuan_moon_bigtts", ["seed-tts-2.0", "seed-tts-1.0"]),
    ("tianmeiyueyue_甜美悦悦",  "zh_female_tianmeiyueyue_moon_bigtts",   ["seed-tts-2.0", "seed-tts-1.0"]),
    ("lanxiaoyangma_懒音萌宝",  "zh_female_lanxiaoyangma_mars_bigtts",   ["seed-tts-2.0", "seed-tts-1.0"]),
    # 角色扮演("tob")系列,萌向拉满;两种前缀都试,不确定哪个在这把 key 上生效
    ("keainvsheng_可爱女生_icl", "ICL_zh_female_keainvsheng_tob",        ["seed-tts-2.0"]),
    ("bingjiaomengmei_病娇萌妹", "ICL_zh_female_bingjiaomengmei_tob",    ["seed-tts-2.0"]),
    ("jiaoruoluoli_娇弱萝莉",   "ICL_zh_female_jiaoruoluoli_tob",        ["seed-tts-2.0"]),
]

OUT = Path("voice_samples")


async def probe(label: str, voice: str, resources: list[str], persona: str, text: str) -> None:
    payload = {
        "user": {"uid": "probe"},
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": 0},
            "additions": json.dumps({"disable_markdown_filter": True}),
        },
    }
    for res in resources:
        headers = {"X-Api-Key": API_KEY, "X-Api-Resource-Id": res, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(ENDPOINT, headers=headers, json=payload)
        except Exception as e:
            print(f"  {label}/{persona} [{res}] 网络错误 {e}")
            continue
        if r.status_code != 200:
            print(f"  {label}/{persona} [{res}] HTTP {r.status_code} {r.text[:150]}")
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
            p = OUT / f"_cute_{label}_{persona}.mp3"
            p.write_bytes(b"".join(chunks))
            print(f"  ✓ {label}/{persona}  speaker={voice}  resource={res}  → {p.name}")
            return
        print(f"  {label}/{persona} [{res}] 空音频")
    print(f"  ✗ {label}/{persona} 全部 resource 都失败")


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    for label, voice, resources in CANDIDATES:
        for persona, text in TEXTS.items():
            await probe(label, voice, resources, persona, text)


if __name__ == "__main__":
    asyncio.run(main())
