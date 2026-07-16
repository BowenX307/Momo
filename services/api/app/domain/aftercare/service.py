"""拍立得 Aftercare 生成：一次轻量 LLM 调用，同时判情绪档 + 按人格口吻写金句。

设计要点：
- **自包含**，直接用 httpx 调 DeepSeek（只读 settings 里已有字段），不依赖 deepseek.py
  里的任何函数——那个文件在服务器上是分叉版本，部署时不希望被牵连。
- 任何失败（无 key / 超时 / JSON 解析不出）都**静默兜底**返回 curated 金句，
  保证相机永远能出片。
"""

import json
import re

import httpx

from app.core.config import settings
from app.domain.aftercare.schemas import AftercareRequest, AftercareResponse, Mood

# 人格口吻提示（内联，避免 import 分叉的 deepseek.py）
_PERSONA_VOICE: dict[str, str] = {
    "youyou": "你是优优，高洞察、有点毒嘴的少年朋友。可以先俏皮损一句，但落点一定要接住情绪、是温柔的。",
    "nini": "你是妮妮，白斗篷小精灵，知性直接，擅长把大问题变小、给一个具体的小台阶。",
}

# 每个情绪档的兜底金句（模型失败时用，和前端 curated 一致的调性）
_FALLBACK: dict[str, str] = {
    "down": "不是所有问题都要今晚解决，\n今晚的任务，只是好好活到明天。",
    "anxious": "脑子转太快的时候，\n先停一下，喝口水，再看。",
    "calm": "你今天已经做得够多了，\n剩下的，交给明天。",
}

_VALID_MOODS: tuple[Mood, ...] = ("down", "anxious", "calm")

_SYSTEM = """你是陪伴体于你的"拍立得售后"生成器。用户刚和你聊完，你要根据这次对话，
产出一张拍立得的背面内容：先判断用户此刻的整体情绪，再写一句写给 ta 的金句。

只输出一个 JSON 对象，不要任何解释、不要代码块围栏：
{"mood": "<down|anxious|calm>", "quote": "<金句>"}

mood 三选一：
- down：失落、难过、压抑、疲惫、委屈、孤独、无力
- anxious：焦虑、迷茫、无奈、烦躁、压力大、想太多
- calm：平静、放松、开心、被安顿好

quote 要求：
- 紧扣这次对话真正聊的那件事，让 ta 觉得"这是写给我今晚的"，不是万能鸡汤。
- 1~2 短句，总共不超过 34 个字；可以用一个 \\n 分成两行。
- 是拍完照写在背面的那种私人、温度感的话；不要引号、不要署名、不要 emoji。
- 口吻符合下面这个人格。"""


def _fallback(mood: Mood = "calm") -> AftercareResponse:
    return AftercareResponse(mood=mood, quote=_FALLBACK[mood], is_mock=True)


def _parse(content: str) -> AftercareResponse | None:
    """从模型输出里抠出 {mood, quote}。抠不出返回 None。"""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    mood = obj.get("mood")
    quote = obj.get("quote")
    if mood not in _VALID_MOODS or not isinstance(quote, str) or not quote.strip():
        return None
    return AftercareResponse(mood=mood, quote=quote.strip(), is_mock=False)


async def generate_aftercare(request: AftercareRequest) -> AftercareResponse:
    """据对话历史生成拍立得内容。失败静默兜底，永不抛错。"""
    # 还没聊 / 没配 key：直接兜底，省一次调用
    if not request.history or not settings.deepseek_api_key:
        return _fallback()

    persona_voice = _PERSONA_VOICE.get(request.persona.value, _PERSONA_VOICE["nini"])
    convo = "\n".join(
        f"{'用户' if m.role == 'user' else '于你'}：{m.content}" for m in request.history
    )
    messages = [
        {"role": "system", "content": f"{_SYSTEM}\n\n【人格】{persona_voice}"},
        {"role": "user", "content": f"这是刚才的对话：\n{convo}\n\n请生成 JSON。"},
    ]
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 120,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.deepseek_base_url}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            return _fallback()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return _fallback()

    return _parse(content) or _fallback()
