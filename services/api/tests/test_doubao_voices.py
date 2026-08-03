"""[2026-08-03] 人格 → 音色参数的映射。

之前完全没有测试覆盖：这套配置只是一个 dict，改错了不会报错、跑不出异常，
只有真人听到"声音变了"才会发现——而 TTS 要花钱、要部署，反馈链路很长。

这里锁住的是 **产品试听定档时的那组参数**。试音样本按 rate=0 / pitch=0 / 无 SSML 停顿
生成，产品据此选定，所以线上必须是同一组合；任何一项被改回默认值，线上听感就和
产品听过的不是一回事了。
"""

import json

import httpx
import pytest
import respx

from app.tts.doubao import _ENDPOINT, _PERSONA_VOICE_OVERRIDES, DoubaoTTSProvider


def _sent_payload(route) -> dict:
    return json.loads(route.calls[0].request.content)["req_params"]


def _sent_headers(route) -> httpx.Headers:
    return route.calls[0].request.headers


async def _synthesize(persona: str):
    """跑一次合成并把发出去的请求截下来。

    data 必须是非空的合法 base64：provider 拿不到音频块会抛 TTSError，
    我们要看的是"发出去的请求长什么样"，不能卡在返回值上。
    """
    chunk = json.dumps({"code": 0, "message": "", "data": "//uQxAA="}) + "\n"
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(_ENDPOINT).mock(return_value=httpx.Response(200, text=chunk))
        await DoubaoTTSProvider().synthesize("今天过得怎么样呀，说说看。", persona=persona)
        return _sent_payload(route), _sent_headers(route)


# ── 音色分配 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_youyou_uses_jiaxiaozi() -> None:
    payload, _ = await _synthesize("youyou")
    assert payload["speaker"] == "ICL_uranus_zh_female_jiaxiaozi_tob"


@pytest.mark.asyncio
async def test_nini_uses_huopodiaoman() -> None:
    payload, _ = await _synthesize("nini")
    assert payload["speaker"] == "ICL_uranus_zh_female_huopodiaoman_tob"


# ── ICL 系列的硬性要求 ──────────────────────────────────────────────────


@pytest.mark.parametrize("persona", ["youyou", "nini"])
def test_icl_voices_must_use_seed_tts_2(persona: str) -> None:
    """ICL_ 前缀的音色只在 seed-tts-2.0 下可用。

    配成 seed-tts-1.0 会报 `app key not found in header or query`——这个报错极具
    误导性，曾让我们误判成"整个音色分类需要在控制台单独建应用"，白白搁置了几天。
    """
    override = _PERSONA_VOICE_OVERRIDES[persona]
    assert str(override["speaker"]).startswith("ICL_")
    assert override["resource_id"] == "seed-tts-2.0"


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", ["youyou", "nini"])
async def test_resource_id_goes_into_header(persona: str) -> None:
    """resource_id 是走请求头的，不在 body 里——写错位置会静默用回默认值。"""
    _, headers = await _synthesize(persona)
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"


# ── 产品定档时的参数组合 ────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", ["youyou", "nini"])
async def test_rate_is_zero_as_auditioned(persona: str) -> None:
    """产品试听 0 / +5 两档后选了 0。"""
    payload, _ = await _synthesize(persona)
    assert payload["audio_params"]["speech_rate"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", ["youyou", "nini"])
async def test_pitch_is_zero_not_global_default(persona: str) -> None:
    """全局 pitch 是 -2(降调)，试音样本是原声。

    漏写这一项两个人格都会被降调，线上听感和产品听过的样本对不上。
    """
    payload, _ = await _synthesize(persona)
    additions = json.loads(payload["additions"])
    assert additions["post_process"]["pitch"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", ["youyou", "nini"])
async def test_no_ssml_pause_injection(persona: str) -> None:
    """natural_pauses 默认 True 会插 300ms 停顿；试音样本是纯文本。"""
    payload, _ = await _synthesize(persona)
    assert "<break" not in payload["text"]
    assert "<speak>" not in payload["text"]


# ── 兜底行为 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_persona_falls_back_to_global_voice() -> None:
    """没配过的人格仍走全局默认，不能因为查不到 override 就崩。"""
    payload, _ = await _synthesize("not-a-persona")
    assert not payload["speaker"].startswith("ICL_")
