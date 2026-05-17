"""SceneClassifier 单元测试。

DeepSeekClassifier 通过 respx mock httpx；MockClassifier 走真实关键词规则。
"""

import httpx
import pytest
import respx

from app.core.config import settings
from app.domain.conversation.schemas import Scene
from app.llm.classifier import DeepSeekClassifier, MockClassifier


def _ok_payload(scene_token: str) -> dict:
    return {
        "choices": [{"message": {"content": scene_token}}],
    }


# --- DeepSeekClassifier ---------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_classifier_returns_scene_on_valid_token():
    classifier = DeepSeekClassifier()
    url = f"{settings.deepseek_base_url}/chat/completions"
    with respx.mock(assert_all_called=True) as mock:
        mock.post(url).mock(
            return_value=httpx.Response(200, json=_ok_payload("relationship"))
        )
        scene = await classifier.classify("他今天又跟我吵了一架")
    assert scene == Scene.RELATIONSHIP


@pytest.mark.asyncio
async def test_deepseek_classifier_strips_punctuation_and_whitespace():
    """模型偶尔会在 token 后带句号/换行/引号——分类器需要清洗。"""
    classifier = DeepSeekClassifier()
    url = f"{settings.deepseek_base_url}/chat/completions"
    with respx.mock() as mock:
        mock.post(url).mock(
            return_value=httpx.Response(200, json=_ok_payload(" Late_Night.\n"))
        )
        scene = await classifier.classify("今晚怎么也睡不着")
    assert scene == Scene.LATE_NIGHT


@pytest.mark.asyncio
async def test_deepseek_classifier_falls_back_on_invalid_token():
    classifier = DeepSeekClassifier()
    url = f"{settings.deepseek_base_url}/chat/completions"
    with respx.mock() as mock:
        mock.post(url).mock(
            return_value=httpx.Response(200, json=_ok_payload("garbage_value"))
        )
        scene = await classifier.classify("不知道说什么")
    assert scene == Scene.LONELINESS


@pytest.mark.asyncio
async def test_deepseek_classifier_falls_back_on_http_error():
    classifier = DeepSeekClassifier()
    url = f"{settings.deepseek_base_url}/chat/completions"
    with respx.mock() as mock:
        mock.post(url).mock(return_value=httpx.Response(500))
        scene = await classifier.classify("好累")
    assert scene == Scene.LONELINESS


@pytest.mark.asyncio
async def test_deepseek_classifier_falls_back_on_timeout():
    classifier = DeepSeekClassifier()
    url = f"{settings.deepseek_base_url}/chat/completions"
    with respx.mock() as mock:
        mock.post(url).mock(side_effect=httpx.TimeoutException("slow"))
        scene = await classifier.classify("好累")
    assert scene == Scene.LONELINESS


# --- MockClassifier -------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected",
    [
        ("今晚怎么都睡不着", Scene.LATE_NIGHT),
        ("我跟我男朋友分手了", Scene.RELATIONSHIP),
        ("最近压力太大撑不住了", Scene.STRESS),
        ("这件事我反复想了一整天", Scene.RUMINATION),
        ("就是想说点什么", Scene.LONELINESS),
        ("", Scene.LONELINESS),
    ],
)
async def test_mock_classifier_keyword_routing(text: str, expected: Scene):
    scene = await MockClassifier().classify(text)
    assert scene == expected
