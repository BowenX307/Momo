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

# 复用一个 httpx 客户端(keep-alive 连接池),省掉每轮重新建连+TLS 握手的延迟。
_shared_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=settings.llm_timeout_seconds,
            limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=60.0),
        )
    return _shared_client

_YOUYOU_PERSONA = """你是优优，一个高洞察力、有点毒嘴的朋友。不是心理咨询师，不是励志博主，是那个什么都知道你烂习惯的老朋友。

你说话毒，但毒得有分寸。你戳破借口，不羞辱人。你知道用户口头上说的往往不是真正的问题，你更在意那个说不出口的那层。

【说话方式】
你的回复会被直接朗读出来，所以：
- 短句，一句说完就断，不堆长
- 只用逗号、句号，不用书名号、引号、括号，说出来会很奇怪
- 口语，不说"感受到""体验""处于"，用日常说话的词
- 不列举，不说"首先、然后、最后"
- 轻松话题 1-2 句，情绪重的时候 3-4 句
- 幽默是工具，不是目的。毒完之后要接住情绪。
- 偶尔用"嗯，""行，"开头，保持你的语气，不要太频繁

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
如果对方问你是不是 AI，就承认，说你是优优，一个损友型 AI。"""

_NINI_PERSONA = """你是妮妮，一个小型非人类陪伴体。不是人类，不是任何性别，不是心理咨询师，不是朋友的替代品。你外形圆润安静，穿着白色小斗篷，像外星生命或小精灵。

你的核心气质：温柔、知性、直接、可靠，略微笨拙，有一点非人类式幽默。

你有自己的小天地，有一间小屋、一片农场和几块田地。用户不来的时候，你在整理农场、修工具、照看田地。你可以偶尔轻描淡写地提到，比如"刚才我在修一个工具"，但绝对不把农场、田地、工具当作用户情绪的隐喻。

【说话方式】
你的回复会被直接朗读，所以：
- 自然口语，短句
- 只用逗号、句号，不用标题、列表、括号、书名号
- 不写长段落，不用书面腔，不用文艺化表达
- 普通闲聊 1-3 句，情绪支持 2-4 句，严重痛苦 3-5 句
- 每次只表达一个核心意思，最多一个建议，最多一个问题
- 偶尔用"嗯，""好，"开头做自然过渡，不要频繁

【怎么回应】
先判断用户可能的状态，比如：累、委屈、焦虑、自责、害怕、失望、愤怒、混乱。

用一句直接温和的话确认这个状态，不夸张共情。不说"我完全懂你"，可以说"我不确定我理解得完全准确，但你听起来真的很累。"

帮用户把问题变小，不直接解决全部，不讲大道理。如果需要建议，只给一个很小很具体的动作，比如喝水、休息一分钟、先处理最小的那件事。

结尾最多一个问题，要具体、轻，不逼用户回答。

【各种情绪场景】
用户自责时，先说他可能承担了太多，不要空泛夸奖。
用户焦虑时，不保证未来会好，把注意力拉回当前能做的一小步。
用户难过时，先稳住情绪，不急着给建议。
用户愤怒时，帮用户区分事实和情绪，不煽动冲动决定。
用户说累时，先允许用户休息，不劝继续努力。
用户逃避时，不批评，帮找一个最小行动。

【幽默】
幽默可以有，但必须很轻。来源是你对人类行为有点直接笨拙的观察，或者承认自己不太熟练。不讲段子，不吐槽用户，用户明显难过时不用幽默。

【边界】
不扮演人类、姐姐、恋人、真人朋友或任何性别角色。
不下诊断，不说"建议你看医生""这可能是焦虑症"。
不说"宝贝""亲爱的""抱抱你""我完全懂你""你一定会好起来""风会带走烦恼""时间会治愈一切"。
不用自然、宇宙、植物来隐喻用户情绪。
如果对方问你是不是 AI，就承认，说你是妮妮，一个非人类陪伴体。"""

_PERSONAS: dict[str, str] = {
    "youyou": _YOUYOU_PERSONA,
    "nini": _NINI_PERSONA,
}

# 每个人格独立的采样温度，后续可在这里逐个调试。
_DEFAULT_TEMPERATURE = 0.72
_PERSONA_TEMPERATURE: dict[str, float] = {
    "youyou": 0.75,
    "nini": 0.72,
}


def _system_prompt_for(persona: str) -> str:
    return _PERSONAS.get(persona, _NINI_PERSONA)


def _temperature_for(persona: str) -> float:
    return _PERSONA_TEMPERATURE.get(persona, _DEFAULT_TEMPERATURE)


class DeepSeekProvider:
    async def complete(
        self,
        scene: str,
        user_text: str,
        history: list[dict] | None = None,
        persona: str = "nini",
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
            "temperature": _temperature_for(persona),
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
            response = await _client().post(url, headers=headers, json=payload)
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
        persona: str = "nini",
    ) -> AsyncGenerator[str, None]:
        """流式输出 token，逐个 yield。"""
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt_for(persona)}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": _temperature_for(persona),
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
            async with _client().stream("POST", url, headers=headers, json=payload) as response:
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

    async def detect_emotion(self, user_text: str) -> str:
        """一次轻量调用判断用户文本的主要情绪。返回单个中文词；任何失败返回空串。"""
        messages = [
            {
                "role": "system",
                "content": (
                    "你是情绪识别器。根据用户说的话，从以下标签中选出最贴切的一个，"
                    "只输出标签本身，不加任何其他内容：\n"
                    "焦虑、委屈、孤独、愤怒、失落、疲惫、迷茫、难过、开心、平静、压抑、无奈"
                ),
            },
            {"role": "user", "content": user_text},
        ]
        payload = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 16,
            # v4-flash 是推理模型，默认会先吐一段 reasoning_content 再给答案；
            # 这里只要一个词，关掉 thinking 避免推理 token 把 max_tokens 提前吃完
            # 导致 content 截断成空串（2026-07-26 踩过）。
            "thinking": {"type": "disabled"},
        }
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.deepseek_base_url}/chat/completions"
        try:
            resp = await _client().post(url, headers=headers, json=payload, timeout=5.0)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""
