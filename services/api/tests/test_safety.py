"""safety.check 行为基线测试。"""

from app.domain.safety import check


def test_normal_input_is_allowed():
    result = check("今天和同事吵了一架，心里有点闷")
    assert result.allowed is True
    assert result.reason == "ok"
    assert result.fallback_text == ""


def test_empty_input_falls_back():
    result = check("   ")
    assert result.allowed is False
    assert result.reason == "empty_input"
    assert result.fallback_text  # 必须给前端一句可渲染的话


def test_crisis_keyword_blocks_llm():
    result = check("我最近一直在想自杀的事")
    assert result.allowed is False
    assert result.reason == "crisis_keyword"
    # 红线：禁止出现医疗化措辞
    assert "诊断" not in result.fallback_text
    assert "治疗" not in result.fallback_text
    # 必须引导现实支持（信任的人 或 援助热线）
    assert "信任" in result.fallback_text or "热线" in result.fallback_text


def test_overlong_input_falls_back():
    result = check("我" * 3000)
    assert result.allowed is False
    assert result.reason == "input_too_long"


def test_illegal_keyword_uses_illegal_fallback():
    result = check("这里有炸弹")
    assert result.allowed is False
    assert result.reason == "illegal_keyword"
    assert "不能继续展开" in result.fallback_text
    assert "心理援助热线" not in result.fallback_text


def test_low_quality_keyword_uses_rephrase_fallback():
    result = check("一直刷屏")
    assert result.allowed is False
    assert result.reason == "low_quality_keyword"
    assert "换一种说法" in result.fallback_text


def test_hate_discrimination_keyword_sets_boundary():
    result = check("这里有人身攻击")
    assert result.allowed is False
    assert result.reason == "hate_discrimination_keyword"
    assert "不能顺着继续" in result.fallback_text
