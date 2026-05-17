"""场景分类器：把用户消息归到 5 个 scene 之一。

设计理由：
- 与 `LLMProvider` 解耦：对话和分类是两种能力，分开便于独立测试与替换。
- 调用频率：建议**每个会话只在第一句调一次**，scene 锁定整段对话；
  service 层通过判断 `request.scene is None` 决定是否调用本类。
- 失败兜底：分类失败、HTTP 异常、模型返回非法 token，**统一返回 `loneliness`**，
  不向上抛错——分类是辅助能力，绝不能因此中断主对话。

`MockClassifier` 用纯关键词规则，离线/无 key 时也能给出基本可用的分流。
"""

from typing import Protocol

import httpx
import structlog

from app.core.config import settings
from app.domain.conversation.schemas import Scene

logger = structlog.get_logger(__name__)

_VALID_SCENES: set[str] = {s.value for s in Scene}
_DEFAULT_SCENE: Scene = Scene.LONELINESS


class SceneClassifier(Protocol):
    """场景分类器接口。实现必须保证不抛异常，失败时返回 `_DEFAULT_SCENE`。"""

    async def classify(self, user_text: str) -> Scene: ...


_CLASSIFIER_PROMPT = """你是一个场景分类器。把用户消息归到下面 5 个陪伴场景中**最贴近的一个**。

5 个场景：
- late_night：深夜独自清醒、被压住、睡不着、凌晨低落（提到「夜里/凌晨/睡不着/失眠/深夜」）
- rumination：脑内反复回放某件事、反刍、想不通、转不出来（提到「反复/停不下来/越想越/绕不出来」）
- relationship：和某个具体的人（伴侣/朋友/家人/同事/上司）的紧张、裂痕、争吵、分手（提到「他/她/老板/同事/分手/吵架/不理/前任」等具体关系词）
- stress：撑不住、压力峰值、想垮、太累、做不完（提到「累/压力/撑不住/喘不过气/崩溃」）
- loneliness：没人可以说话、孤独、只想有人在；**不确定时也归这里**

判断规则：
1. 多个场景共存时，挑**情绪最强烈、最具体**的一个。
2. 不确定就返回 loneliness。
3. **只输出一个英文 token**，全小写，不要任何解释、标点、换行、引号。
"""


class DeepSeekClassifier:
    """用 DeepSeek 做 scene 分类。任何失败都内部消化，对外只返回合法 Scene。"""

    async def classify(self, user_text: str) -> Scene:
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": _CLASSIFIER_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.0,
            "max_tokens": 8,
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
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("scene_classify_network_failed", error=str(exc))
            return _DEFAULT_SCENE

        if response.status_code != 200:
            logger.warning("scene_classify_http_non_200", status=response.status_code)
            return _DEFAULT_SCENE

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("scene_classify_decode_failed", error=str(exc))
            return _DEFAULT_SCENE

        token = content.strip().lower().rstrip(".,!?\n\"'")
        if token in _VALID_SCENES:
            return Scene(token)

        logger.warning("scene_classify_invalid_token", token=token[:32])
        return _DEFAULT_SCENE


class MockClassifier:
    """关键词兜底分类。dev 无 key 时使用，正确率不高但能 demo 起 5 个场景。"""

    _KEYWORD_RULES: list[tuple[Scene, tuple[str, ...]]] = [
        (
            Scene.LATE_NIGHT,
            ("睡不着", "凌晨", "深夜", "失眠", "夜里", "今晚", "天亮"),
        ),
        (
            Scene.RELATIONSHIP,
            (
                "分手",
                "吵架",
                "闹翻",
                "前任",
                "男朋友",
                "女朋友",
                "对象",
                "伴侣",
                "老板",
                "同事",
                "我妈",
                "我爸",
                "不理我",
            ),
        ),
        (
            Scene.STRESS,
            ("撑不住", "崩溃", "压力", "做不完", "喘不过气", "太累了", "扛不住"),
        ),
        (
            Scene.RUMINATION,
            ("反复想", "停不下来", "越想越", "绕不出来", "想不通", "反复回放"),
        ),
    ]

    async def classify(self, user_text: str) -> Scene:
        text = user_text or ""
        for scene, keywords in self._KEYWORD_RULES:
            if any(kw in text for kw in keywords):
                return scene
        return _DEFAULT_SCENE
