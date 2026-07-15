"""
MOMO 声音试听脚本
运行：uv run python try_voices.py
会在 ./voice_samples/ 目录下生成 MP3，用 Finder 打开直接双击试听。
"""

import asyncio
import base64
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("DOUBAO_TTS_API_KEY", "")
ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

# MOMO 典型台词——包含停顿、语气词，能充分暴露人机感
SAMPLE_TEXT = "嗯，我在呢。不管今天发生了什么，你都可以跟我说。有时候把心里压着的东西说出来，会好受一点的。"

# 候选声音：(label, voice_id, model)
CANDIDATES = [
    # ---- 1.0 基准（对比用）----
    ("00_baseline_1.0",      "zh_female_shuangkuaisisi_moon_bigtts",  "seed-tts-1.0"),
    # ---- 2.0 通用场景女声 ----
    ("01_2.0_xiaohe",        "zh_female_xiaohe_uranus_bigtts",        "seed-tts-2.0"),  # 小何
    ("02_2.0_vivi",          "zh_female_vv_uranus_bigtts",            "seed-tts-2.0"),  # vivi 2.0
    # ---- 2.0 角色扮演女声（成熟/个性）----
    ("03_2.0_cancan",        "saturn_zh_female_cancan_tob",           "seed-tts-2.0"),  # 知性灿灿
    ("04_2.0_keainvsheng",   "saturn_zh_female_keainvsheng_tob",      "seed-tts-2.0"),  # 可爱女生
    ("05_2.0_tiaopigongzhu", "saturn_zh_female_tiaopigongzhu_tob",   "seed-tts-2.0"),  # 调皮公主
    # ---- 2.0 男声（温暖成熟对比）----
    ("06_2.0_yunshu",        "zh_male_m191_uranus_bigtts",            "seed-tts-2.0"),  # 云舟
    ("07_2.0_xiaotian",      "zh_male_taocheng_uranus_bigtts",        "seed-tts-2.0"),  # 小天
]

OUT_DIR = Path("voice_samples")


async def render(label: str, voice: str, model: str) -> None:
    payload = {
        "user": {"uid": "momo_test"},
        "req_params": {
            "text": SAMPLE_TEXT,
            "speaker": voice,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": -8,
            },
            "additions": json.dumps({
                "post_process": {"pitch": -2.0},
                "disable_markdown_filter": True,
            }),
        },
    }
    headers = {
        "X-Api-Key": API_KEY,
        "X-Api-Resource-Id": model,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(ENDPOINT, headers=headers, json=payload)

    if resp.status_code != 200:
        print(f"  ✗ {label}: HTTP {resp.status_code} — {resp.text[:200]}")
        return

    chunks: list[bytes] = []
    for line in resp.content.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("data"):
            chunks.append(base64.b64decode(obj["data"]))

    if not chunks:
        print(f"  ✗ {label}: 返回了空音频，原始响应前 3 行：")
        for line in resp.content.split(b"\n")[:3]:
            if line.strip():
                print(f"       {line.decode(errors='replace')}")
        return

    out = OUT_DIR / f"{label}.mp3"
    out.write_bytes(b"".join(chunks))
    size_kb = out.stat().st_size // 1024
    print(f"  ✓ {label}.mp3  ({size_kb} KB)")


async def main() -> None:
    if not API_KEY:
        print("错误：.env 里没有 DOUBAO_TTS_API_KEY")
        return

    OUT_DIR.mkdir(exist_ok=True)
    print(f"试听台词：{SAMPLE_TEXT}\n")
    print("开始渲染，请稍候…\n")

    for label, voice, model in CANDIDATES:
        print(f"  → {label} [{model}]")
        await render(label, voice, model)

    print(f"\n全部完成！打开 {OUT_DIR.resolve()} 文件夹，双击 MP3 对比试听。")
    # macOS：直接用 Finder 打开
    import subprocess
    subprocess.run(["open", str(OUT_DIR)], check=False)


asyncio.run(main())
