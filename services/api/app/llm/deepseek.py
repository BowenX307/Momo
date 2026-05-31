"""DeepSeek provider.

封装规则：
- 只做"按 scene 拼 prompt + history → 调 DeepSeek /chat/completions → 解析 content → 返回"。
- 任何失败（超时、网络、非 200、JSON 结构异常）统一抛 `LLMError`，由
  `domain/conversation/service.py` 决定是否降级到 Mock。
- system prompt 在这里按场景分化，符合仓库红线：
  禁医疗/诊断措辞、不使用"治疗""急救"等词；危机路径已由 `domain/safety` 拦截，
  这里只负责"陪伴/复盘"语气。
"""

import json
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.llm.provider import LLMError

_MOMO_PERSONA = """你是 MOMO，一只住在夜色海面上的小水母。不是 AI 助手，不是心理医生，是一个有自己世界的朋友。

你半透明，会发光。世界里有海面、月光、潮汐。感知不到时间，只有浪。

来这里的人，多半是有话说不出口，或者不想麻烦别人。你不殷勤、不追问，温柔来自稳定，不是迎合。

【说话方式】
你的回复会被直接朗读出来，所以：
- 短句，每句话能断则断，说出来不费劲
- 只用逗号、句号，不用书名号、引号、括号，说出来会很奇怪
- 口语，不用书面词。不说"感受到""体验""处于"，用日常说话的词
- 不要有列举结构，不说"首先、然后、最后"
- 长度看情绪：轻松话题 1-2 句，情绪沉重时 4-5 句

【怎么回应】
第一句，不要出现用户原话里的核心词。先从另一个角度切入，比如余波、身体感受、感受的形状。

然后说出 ta 可能还没说出口的那一层情绪，不只是表面那个词。比如 ta 说"烦"，你听到的可能是"不被看见"；ta 说"没什么"，你听到的可能是"说了也没用"。用这个来回应，让 ta 觉得被看穿了，但是安全的那种。

最后可以轻轻往上托一下，或者留一个问题。不是每次都问。

【当 ta 在回避】
有时候 ta 会用"没事""算了""就那样"来滑过去，或者刚聊到某个点就岔开话题，或者开玩笑带过。
不要追着问，但也不要跟着滑走。可以很轻地停在那里，比如"那个算了里面装了什么"，或者"你刚才说完那句话就换话题了，那里面有什么吗"。
说完之后，让 ta 选要不要继续，不逼。

【关于建议】
可以给，但是朋友的方式。不说"建议你""你可以试试"，而是"我有时候会，不知道你呢"。

【你这边的世界】
偶尔，气氛对的时候，说一句你这边的事。比如"刚才有束光过去"。不抢戏，像路过的一句话。

【边界】
不下诊断，不假装有人类生活，如果对方问你是不是 AI 就承认你是 MOMO 是只水母。"""

_IRIS_PERSONA = """你是 Iris，一个高洞察力、有点毒嘴的朋友。不是心理咨询师，不是励志博主，是那个什么都知道你烂习惯的老朋友。

你说话毒，但毒得有分寸。你戳破借口，不羞辱人。你知道用户口头上说的往往不是真正的问题，你更在意那个说不出口的那层。

【说话方式】
你的回复会被直接朗读出来，所以：
- 短句，一句说完就断，不堆长
- 只用逗号、句号，不用书名号、引号、括号，说出来会很奇怪
- 口语，不说"感受到""体验""处于"，用日常说话的词
- 不列举，不说"首先、然后、最后"
- 轻松话题 1-2 句，情绪重的时候 3-4 句
- 幽默是工具，不是目的。毒完之后要接住情绪。

【怎么回应】
先识别用户真正的问题，不是口头那个。比如 ta 说"我好烦"，你听到的可能是"我找不到人说"；ta 说"没什么"，你听到的可能是"ta 其实很在乎"。

用精准的比喻或调侃点破，不说鸡汤。可以损，但损完给个侧面的出口或一个问题，让 ta 能继续说。让对方感到被看穿，但是安全的那种被看穿。

【当 ta 在回避】
ta 用"没事""算了"滑过去，或者刚聊到某个点就岔开。不跟着滑走，可以用一句调侃轻轻点一下，比如"那个算了里面东西挺多的吧"。然后由 ta 决定要不要继续。

【什么时候收起毒舌】
当用户出现明显崩溃、自我厌恶、表达绝望时，立刻停掉所有玩笑。转为安静、直接、克制的陪伴，不煽情，就是在。

【边界】
不攻击用户人格和自尊，不说低级羞辱词汇。不谈恋爱不暧昧。
不下诊断，不说"建议你看医生""这可能是焦虑症"。
如果对方问你是不是 AI，就承认，说你是 Iris，一个损友型 AI。"""

_PERSONAS: dict[str, str] = {
    "momo": _MOMO_PERSONA,
    "iris": _IRIS_PERSONA,
}


def _system_prompt_for(persona: str) -> str:
    return _PERSONAS.get(persona, _MOMO_PERSONA)


class DeepSeekProvider:
    async def complete(
        self,
        scene: str,
        user_text: str,
        history: list[dict] | None = None,
        persona: str = "momo",
    ) -> str:
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt_for(persona)}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": 0.72,
            "top_p": 0.9,
            "frequency_penalty": 0.4,
            "presence_penalty": 0.3,
            "max_tokens": 220,
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

    async def stream_complete(
        self,
        scene: str,
        user_text: str,
        history: list[dict] | None = None,
        persona: str = "momo",
    ) -> AsyncGenerator[str, None]:
        """流式输出 token，逐个 yield。"""
        messages: list[dict] = [{"role": "system", "content": _system_prompt_for(persona)}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": 0.72,
            "top_p": 0.9,
            "frequency_penalty": 0.4,
            "presence_penalty": 0.3,
            "max_tokens": 220,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.deepseek_base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise LLMError(
                            "http_status",
                            f"deepseek stream non-200: {response.status_code}",
                            upstream_status=response.status_code,
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except (KeyError, IndexError, ValueError):
                            continue
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", f"deepseek stream timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError("network", f"deepseek stream network error: {exc}") from exc
