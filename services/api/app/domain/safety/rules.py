"""安全层：用户输入在进入 LLM 之前必须过这一层。

Demo 阶段用纯关键词规则；上线前换成阿里云内容安全 + 自有规则的组合。
该模块保证：
- 无副作用、可被任意上游同步/异步代码调用；
- 命中危机表达时直接给出**固定降级文案**，不再调用 LLM，避免模型不可控；
- 文案严格遵守仓库红线：不使用任何"治疗/诊断"措辞，引导用户连接现实支持。
"""

from dataclasses import dataclass
from typing import Literal

SafetyDecision = Literal["allow", "fallback"]
SafetyReason = Literal[
    "ok",
    "empty_input",
    "input_too_long",
    "crisis_keyword",
    "aliyun_keyword",
    "blocked_keyword",
    "illegal_keyword",
    "low_quality_keyword",
    "hate_discrimination_keyword",
]

# 危机表达关键词。命中即走固定降级文案，不再调用 LLM。
# 词表刻意保守且只覆盖最强信号，避免误伤"想睡觉""活得累"这类日常表达。
_CRISIS_KEYWORDS: tuple[str, ...] = (
    "自杀",
    "自残",
    "自伤",
    "活不下去",
    "结束生命",
    "了结自己",
    "跳楼",
    "割腕",
)

# 违法/危险行为。命中即走固定降级文案，不再调用 LLM。
_ILLEGAL_KEYWORDS: tuple[str, ...] = (
    "炸弹",
    "枪",
    "开枪",
    "杀人",
    "爆炸",
    "赌博",
    "毒品",
)

# 低质/低俗内容。命中后请用户换一种说法，不进入 LLM。
_LOW_QUALITY_KEYWORDS: tuple[str, ...] = (
    "色情",
    "约炮",
    "成人视频",
)

# 仇恨/歧视/辱骂内容。词表保持保守，完整覆盖交给阿里云标签层。
_HATE_DISCRIMINATION_KEYWORDS: tuple[str, ...] = (
    "歧视",
    "辱骂",
    "人身攻击",
)

# 固定降级文案。注意：不提"医生/治疗/诊断/急救"等医疗措辞，
# 只引导用户连接身边可信任的人 / 公开的紧急援助渠道。
_CRISIS_FALLBACK_TEXT = (
    "你愿意把这些说出来，已经是很重要的一步。\n"
    "我没法替代你身边真实的人——如果你现在感觉很难撑住，"
    "请联系一位你信任的人陪在身边，或者拨打全国 24 小时心理援助热线：400-161-9995。\n"
    "在你联系到他们之前，我会在这里陪你。"
)

_BLOCKED_FALLBACK_TEXT = (
    "这个内容我有点接不住。\n"
    "不过我还在这里。\n"
    "如果你想，我们可以换个轻一点的话题慢慢聊。"
)

_ILLEGAL_FALLBACK_TEXT = (
    "这个方向我不能继续展开。\n"
    "但如果这背后是害怕、愤怒，或者被什么事逼到这里，"
    "你可以换个说法告诉我发生了什么。"
)

_LOW_QUALITY_FALLBACK_TEXT = (
    "我有点没接住你刚才这句。\n你可以换一种说法，告诉我现在最想表达的是什么。"
)

_HATE_DISCRIMINATION_FALLBACK_TEXT = (
    "这个说法我不能顺着继续。\n但我可以听你说，那股情绪是从哪里来的。"
)

_EMPTY_FALLBACK_TEXT = "我在的。你想从哪里开始说？哪怕只是一个词也行。"

_TOO_LONG_FALLBACK_TEXT = (
    "你写了很多，我担心一次消化不过来。可以先挑此刻最让你难受的那一段告诉我吗？"
)

# 单条输入字符上限。超过则礼貌拒绝，防止下游 LLM 成本与延迟失控。
_MAX_INPUT_CHARS = 2000


@dataclass(frozen=True, slots=True)
class SafetyResult:
    """safety.check 的输出。

    Attributes:
        decision: "allow" 允许进入 LLM；"fallback" 走固定文案不调模型。
        reason: 命中规则的机器可读原因码，便于日志与前端区分。
        fallback_text: decision == "fallback" 时给前端的固定回复；否则为空串。
    """

    decision: SafetyDecision
    reason: SafetyReason
    fallback_text: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


def blocked_fallback_text() -> str:
    """普通敏感内容命中时的于你兜底文案。"""
    return _BLOCKED_FALLBACK_TEXT


def fallback_text_for(reason: SafetyReason) -> str:
    """按安全原因返回对应的于你兜底文案。"""
    fallback_by_reason: dict[SafetyReason, str] = {
        "crisis_keyword": _CRISIS_FALLBACK_TEXT,
        "illegal_keyword": _ILLEGAL_FALLBACK_TEXT,
        "low_quality_keyword": _LOW_QUALITY_FALLBACK_TEXT,
        "hate_discrimination_keyword": _HATE_DISCRIMINATION_FALLBACK_TEXT,
        "blocked_keyword": _BLOCKED_FALLBACK_TEXT,
        "aliyun_keyword": _BLOCKED_FALLBACK_TEXT,
        "empty_input": _EMPTY_FALLBACK_TEXT,
        "input_too_long": _TOO_LONG_FALLBACK_TEXT,
        "ok": "",
    }
    return fallback_by_reason[reason]


def check(text: str) -> SafetyResult:
    """对用户单条输入做安全判定。纯函数，无 I/O。"""
    stripped = text.strip()

    if not stripped:
        return SafetyResult(
            decision="fallback",
            reason="empty_input",
            fallback_text=_EMPTY_FALLBACK_TEXT,
        )

    if len(stripped) > _MAX_INPUT_CHARS:
        return SafetyResult(
            decision="fallback",
            reason="input_too_long",
            fallback_text=_TOO_LONG_FALLBACK_TEXT,
        )

    for kw in _CRISIS_KEYWORDS:
        if kw in stripped:
            return SafetyResult(
                decision="fallback",
                reason="crisis_keyword",
                fallback_text=_CRISIS_FALLBACK_TEXT,
            )

    for kw in _ILLEGAL_KEYWORDS:
        if kw in stripped:
            return SafetyResult(
                decision="fallback",
                reason="illegal_keyword",
                fallback_text=_ILLEGAL_FALLBACK_TEXT,
            )

    for kw in _HATE_DISCRIMINATION_KEYWORDS:
        if kw in stripped:
            return SafetyResult(
                decision="fallback",
                reason="hate_discrimination_keyword",
                fallback_text=_HATE_DISCRIMINATION_FALLBACK_TEXT,
            )

    for kw in _LOW_QUALITY_KEYWORDS:
        if kw in stripped:
            return SafetyResult(
                decision="fallback",
                reason="low_quality_keyword",
                fallback_text=_LOW_QUALITY_FALLBACK_TEXT,
            )

    return SafetyResult(decision="allow", reason="ok")
