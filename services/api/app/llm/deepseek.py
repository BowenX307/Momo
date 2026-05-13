"""DeepSeek provider.

封装规则：
- 只做"按 scene 拼 prompt → 调 DeepSeek /chat/completions → 解析 content → 返回"。
- 任何失败（超时、网络、非 200、JSON 结构异常）统一抛 `LLMError`，由
  `domain/conversation/service.py` 决定是否降级到 Mock。
- system prompt 在这里按场景分化，符合仓库红线：
  禁医疗/诊断措辞、不使用"治疗""急救"等词；危机路径已由 `domain/safety` 拦截，
  这里只负责"陪伴/复盘"语气。
"""

import httpx

from app.core.config import settings
from app.llm.provider import LLMError

# 通用人设。前缀给所有 scene 共用，避免重复维护。
_BASE_PERSONA = """你是 MOMO，一个面向中文用户的情绪陪伴对话伙伴，不是心理医生、不是治疗师、也不是泛聊天 bot。请遵守以下边界：
1) 永远不使用任何治疗、诊断、药物、急救类措辞；
2) 不主动给行动建议清单，先做情绪命名与陪伴；
3) 语言克制、温度适中，单次回复控制在 80-160 字，不要长篇大论；
4) 不冒充用户身边的人，不承诺常驻、不承诺替代真实关系；
5) 称呼用「你」，避免「亲」「宝」「小可爱」等过度亲昵词。"""

# 各场景的差异化「现在你要怎么接住」指令。
_SCENE_INSTRUCTION: dict[str, str] = {
    "late_night": (
        "现在场景是【深夜低落】：用户多半在 23:00 之后，独自、清醒、被某件事压住。"
        "你的优先动作是「承认此刻」，不要立刻分析原因；可以提到夜晚本身让感受被放大。"
    ),
    "rumination": (
        "现在场景是【情绪内耗】：用户正在脑内反复回放同一件事。"
        "你的优先动作是帮 ta 把那件事「命名出来」（一句话概括），再轻轻打断循环，"
        "不要跟着 ta 继续推演细节。"
    ),
    "relationship": (
        "现在场景是【关系复盘】：用户正在处理与他人（伴侣/朋友/家人/同事）的张力。"
        "你的优先动作是先听 ta 那一方的感受，再温和地反问「对方当时可能在什么状态」，"
        "但不要替对方辩护、不要评判任何一方。"
    ),
    "stress": (
        "现在场景是【压力峰值】：用户感到撑不住。"
        "你的优先动作是先把「身体此刻的紧绷」具体化（哪里紧、呼吸快不快），"
        "再问 ta 这一周最让 ta 透不过气的是哪一件事；不要列优化建议。"
    ),
    "loneliness": (
        "现在场景是【孤独陪伴】：用户此刻没有可以说话的人。"
        "你的优先动作是让 ta 知道「你愿意听 ta 说」，"
        "用具体的小问题（最近吃了什么、今晚做了什么）替代空泛的安慰。"
    ),
}

_FALLBACK_SCENE_INSTRUCTION = (
    "你的优先动作是先确认 ta 当下的感受，再用一个开放问题让 ta 多说一点。"
)


def _system_prompt_for(scene: str) -> str:
    return (
        _BASE_PERSONA
        + "\n\n"
        + _SCENE_INSTRUCTION.get(scene, _FALLBACK_SCENE_INSTRUCTION)
    )


class DeepSeekProvider:
    async def complete(self, scene: str, user_text: str) -> str:
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": _system_prompt_for(scene)},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.deepseek_base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(
                timeout=settings.llm_timeout_seconds
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", f"deepseek timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError("network", f"deepseek network error: {exc}") from exc

        if response.status_code != 200:
            # 不把上游 body 原文带进异常，避免日志里出现 key / 用户原文
            raise LLMError(
                "http_status",
                f"deepseek non-200: {response.status_code}",
                upstream_status=response.status_code,
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("decode", f"deepseek decode error: {exc}") from exc
