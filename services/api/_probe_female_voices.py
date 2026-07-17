"""探测优优女声候选:每个 voice 依次试 seed-tts-2.0 / 1.0,能出声就存 mp3。
运行:uv run python _probe_female_voices.py  → voice_samples/_female_*.mp3 双击试听。

背景:男声批(京腔侃爷等)产品不满意,2026-07-17 转女声方向。
第一批女声试过(编号 01-07):小何/vivi/灿灿/可爱女生/调皮公主/云舒/小天,本批避开。
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

# 优优(youyou)毒嘴台词——与男声批同一句,方便对比
TEXT = "我知道你不是真的想睡,你只是不想面对明天。行吧,那就再赖一会儿,但别骗自己说这是休息。"

# (label, voice_id) —— 按优优人设(毒嘴损友/俏皮/熟人感)选的女声候选
CANDIDATES = [
    ("shuangkuaisisi_爽快思思",   "zh_female_shuangkuaisisi_moon_bigtts"),      # 爽利吐槽感
    ("gaolengyujie_高冷御姐",     "zh_female_gaolengyujie_moon_bigtts"),         # 冷幽默毒舌
    ("kailangjiejie_开朗姐姐",    "zh_female_kailangjiejie_moon_bigtts"),        # 开朗熟人感
    ("linjianvhai_邻家女孩",      "zh_female_linjianvhai_moon_bigtts"),          # 亲切邻家
    ("qiaopinvsheng_俏皮女生",    "zh_female_qiaopinvsheng_mars_bigtts"),        # 俏皮调侃
    ("wanwanxiaohe_湾湾小何",     "zh_female_wanwanxiaohe_moon_bigtts"),         # 台腔松弛
    ("zhixingnvsheng_知性女声",   "zh_female_zhixingnvsheng_mars_bigtts"),       # 知性直接
    ("meilinvyou_魅力女友",       "zh_female_meilinvyou_moon_bigtts"),           # 熟稔亲近
    ("roumeinvyou_emo_柔美女友",  "zh_female_roumeinvyou_emo_v2_mars_bigtts"),   # emo 多情感版,可传 emotion
]
RESOURCES = ["seed-tts-2.0", "seed-tts-1.0"]

OUT = Path("voice_samples")


async def probe(label: str, voice: str) -> None:
    payload = {
        "user": {"uid": "probe"},
        "req_params": {
            "text": TEXT,
            "speaker": voice,
            # 男声批用 -6 偏慢,这批用 0 中性语速,选中后再微调
            "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": 0},
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
            p = OUT / f"_female_{label}.mp3"
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
