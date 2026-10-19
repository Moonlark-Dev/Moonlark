"""send_sticker 的 Jev 判定流程测试

新的发送流程：Chat 模型只提供关键词，send_sticker 用关键词在数据库中搜索候选，
再把关键词、最近五条消息与 Moonlark 的思考内容提交给 Jev，由 Jev 选出要发送的
表情包（可决定不发送），置信度过低时不发送，并把实际发送结果作为工具响应返回。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

# ---------------------------------------------------------------- 通用桩

LANG_TEMPLATES = {
    "sticker.search_empty": "没有找到匹配的表情包",
    "sticker.sent_detail": "已发送表情包：{}",
    "sticker.jev_declined": "经过判定，本次不适合发送表情包，没有发送",
    "sticker.low_confidence": "表情包判定的置信度过低（{}），本次没有发送表情包",
    "sticker.judge_failed": "表情包判定暂时不可用，本次没有发送表情包",
}


async def _fake_lang_text(key: str, lang_str: str, *args, **kwargs) -> str:
    return LANG_TEMPLATES[key].format(*args)


def _make_sticker(sticker_id: int = 3, **overrides) -> SimpleNamespace:
    fields = {"id": sticker_id, "description": "猫猫摸头", "meme_text": "", "emotion": "", "raw": b"sticker-bytes"}
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _make_processor(chat_context: str = "[10:00] 小明: 早上好") -> SimpleNamespace:
    session = SimpleNamespace(lang_str="zh_hans", session_id="qq_123456")
    processor = SimpleNamespace(
        session=session,
        openai_messages=SimpleNamespace(fetcher=None),  # 无进行中的请求：取不到思考内容
        _latest_reasioning_content_cache="",
    )
    session.get_cached_messages_string = AsyncMock(return_value=chat_context)
    return processor


def _choice(value: str, confidence: float) -> object:
    from nonebot_plugin_jev.types import ChoiceAnswer

    return ChoiceAnswer(choice=value, confidence=confidence)


# ---------------------------------------------------------------- select_sticker


async def test_select_sticker_state_and_questions() -> None:
    """state 提交关键词/最近消息/思考内容，问题给到候选与 none 选项"""
    from nonebot_plugin_chat.utils import jev_judge

    processor = _make_processor("最近消息")
    processor._latest_reasioning_content_cache = "想回一张猫图"
    candidates = [_make_sticker(1), _make_sticker(2, description="狗头")]

    captured: dict = {}

    async def fake_ask(state, questions, **kwargs):
        captured["state"] = state
        captured["questions"] = questions
        captured["identify"] = kwargs.get("identify")
        return {"pick": _choice("1", 0.9)}

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        selection = await jev_judge.select_sticker(processor, "猫猫", candidates)  # type: ignore[arg-type]

    assert captured["identify"] == "Sticker Selection"
    state = captured["state"]
    assert state["requested_keyword"] == "猫猫"
    assert state["chat_context"] == "最近消息"
    assert state["thinking_content"] == "想回一张猫图"
    # 选项以字符串 ID 为键并带 none 选项，内容是候选的表情包描述
    criteria = captured["questions"]["pick"].criteria
    assert set(criteria) == {"1", "2", "none"}
    assert "猫猫摸头" in criteria["1"]
    assert "狗头" in criteria["2"]

    assert selection.status == "send"
    assert selection.sticker_id == 1
    assert "猫猫摸头" in selection.description


async def test_select_sticker_thinking_prefers_current_round() -> None:
    """进行中的请求里有 reasoning_content 时优先于上一轮缓存"""
    from nonebot_plugin_chat.utils import jev_judge

    processor = _make_processor()
    processor._latest_reasioning_content_cache = "旧思考"
    processor.openai_messages = SimpleNamespace(
        fetcher=SimpleNamespace(
            session=SimpleNamespace(
                messages=[
                    {"role": "user", "content": "你好"},  # 用户消息，跳过继续向上找
                    {"role": "assistant", "content": "回一句", "reasoning_content": "本轮思考"},
                ]
            )
        )
    )

    async def fake_ask(state, questions, **kwargs):
        assert state["thinking_content"] == "本轮思考"
        return {"pick": _choice("none", 0.9)}

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        await jev_judge.select_sticker(processor, "猫猫", [_make_sticker()])  # type: ignore[arg-type]


async def test_select_sticker_declined() -> None:
    """Jev 选择 none：明确决定不发送"""
    from nonebot_plugin_chat.utils import jev_judge

    async def fake_ask(state, questions, **kwargs):
        return {"pick": _choice("none", 0.8)}

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        selection = await jev_judge.select_sticker(_make_processor(), "猫猫", [_make_sticker()])  # type: ignore[arg-type]

    assert selection.status == "declined"
    assert selection.sticker_id is None
    assert selection.confidence == pytest.approx(0.8)


async def test_select_sticker_low_confidence_not_sent() -> None:
    """Jev 置信度过低时不发送"""
    from nonebot_plugin_chat.utils import jev_judge

    async def fake_ask(state, questions, **kwargs):
        return {"pick": _choice("3", 0.3)}

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        selection = await jev_judge.select_sticker(_make_processor(), "猫猫", [_make_sticker(3)])  # type: ignore[arg-type]

    assert selection.status == "low_confidence"
    assert selection.sticker_id == 3


async def test_select_sticker_ask_failure_returns_skipped() -> None:
    """Jev 不可用时返回 skipped，不发送"""
    from nonebot_plugin_chat.utils import jev_judge

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=RuntimeError("no key"))):
        selection = await jev_judge.select_sticker(_make_processor(), "猫猫", [_make_sticker()])  # type: ignore[arg-type]

    assert selection.status == "skipped"


async def test_select_sticker_unknown_choice_returns_skipped() -> None:
    """Jev 返回候选之外的选项时按 skipped 处理"""
    from nonebot_plugin_chat.utils import jev_judge

    with patch.object(jev_judge, "ask", AsyncMock(return_value={"pick": _choice("999", 0.9)})):
        selection = await jev_judge.select_sticker(_make_processor(), "猫猫", [_make_sticker(3)])  # type: ignore[arg-type]

    assert selection.status == "skipped"


async def test_select_sticker_empty_candidates_never_calls_jev() -> None:
    """候选为空时直接返回 skipped，不再请求 Jev"""
    from nonebot_plugin_chat.utils import jev_judge

    ask_mock = AsyncMock()
    with patch.object(jev_judge, "ask", ask_mock):
        selection = await jev_judge.select_sticker(_make_processor(), "猫猫", [])  # type: ignore[arg-type]

    assert selection.status == "skipped"
    ask_mock.assert_not_awaited()


# ---------------------------------------------------------------- send_sticker 工具


def _make_session() -> SimpleNamespace:
    processor = SimpleNamespace(
        token_bucket=SimpleNamespace(add=Mock()),
        openai_messages=SimpleNamespace(fetcher=None),
        _latest_reasioning_content_cache="",
    )
    processor.session = SimpleNamespace(
        lang_str="zh_hans",
        session_id="qq_123456",
        get_cached_messages_string=AsyncMock(return_value="最近消息"),
    )
    return SimpleNamespace(
        lang_str="zh_hans",
        session_id="qq_123456",
        target=object(),
        bot=object(),
        processor=processor,
    )


def _make_tools():
    from nonebot_plugin_chat.utils.tools.sticker import StickerTools

    tools = StickerTools(_make_session())  # type: ignore[arg-type]
    tools.manager = AsyncMock()
    return tools


async def test_send_sticker_sends_jev_choice_and_reports() -> None:
    """Jev 选中的表情包被发送，工具响应告知发送内容"""
    from nonebot_plugin_chat.utils import jev_judge
    from nonebot_plugin_chat.utils.tools import sticker as sticker_mod

    sticker = _make_sticker(3)
    tools = _make_tools()
    tools.manager.search_sticker.return_value = [sticker]
    tools.manager.get_sticker.return_value = sticker

    with (
        patch.object(jev_judge, "ask", AsyncMock(return_value={"pick": _choice("3", 0.9)})),
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
        patch.object(sticker_mod.UniMessage, "image") as image_mock,
    ):
        image_mock.return_value.send = AsyncMock()
        result = await tools.send_sticker("猫猫")

    assert result == "已发送表情包：猫猫摸头"
    image_mock.assert_called_once_with(raw=sticker.raw)
    image_mock.return_value.send.assert_awaited_once()
    tools.session.processor.token_bucket.add.assert_called_once_with(0.5)
    # 只有 AND 搜索命中时不再做 OR 兜底
    tools.manager.search_sticker_any.assert_not_called()


async def test_send_sticker_falls_back_to_any_search() -> None:
    """AND 搜索无结果时回退到 OR 搜索"""
    from nonebot_plugin_chat.utils import jev_judge
    from nonebot_plugin_chat.utils.tools import sticker as sticker_mod

    sticker = _make_sticker(3)
    tools = _make_tools()
    tools.manager.search_sticker.return_value = []
    tools.manager.search_sticker_any.return_value = [sticker]
    tools.manager.get_sticker.return_value = sticker

    with (
        patch.object(jev_judge, "ask", AsyncMock(return_value={"pick": _choice("3", 0.8)})),
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
        patch.object(sticker_mod.UniMessage, "image") as image_mock,
    ):
        image_mock.return_value.send = AsyncMock()
        result = await tools.send_sticker("猫 狗")

    assert result == "已发送表情包：猫猫摸头"
    tools.manager.search_sticker_any.assert_awaited_once()
    image_mock.assert_called_once()


async def test_send_sticker_empty_search_returns_empty_message() -> None:
    """数据库中没有匹配时返回空结果文案，不请求 Jev"""
    from nonebot_plugin_chat.utils import jev_judge

    tools = _make_tools()
    tools.manager.search_sticker.return_value = []
    tools.manager.search_sticker_any.return_value = []

    ask_mock = AsyncMock()
    with (
        patch.object(jev_judge, "ask", ask_mock),
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
    ):
        result = await tools.send_sticker("不存在的关键词")

    assert result == "没有找到匹配的表情包"
    ask_mock.assert_not_awaited()
    tools.manager.get_sticker.assert_not_awaited()


async def test_send_sticker_declined_reports_no_send() -> None:
    """Jev 决定不发送时如实告知，且不发送图片"""
    from nonebot_plugin_chat.utils import jev_judge
    from nonebot_plugin_chat.utils.tools import sticker as sticker_mod

    tools = _make_tools()
    tools.manager.search_sticker.return_value = [_make_sticker(3)]

    with (
        patch.object(jev_judge, "ask", AsyncMock(return_value={"pick": _choice("none", 0.9)})),
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
        patch.object(sticker_mod.UniMessage, "image") as image_mock,
    ):
        result = await tools.send_sticker("猫猫")

    assert result == "经过判定，本次不适合发送表情包，没有发送"
    image_mock.assert_not_called()
    tools.session.processor.token_bucket.add.assert_not_called()


async def test_send_sticker_low_confidence_reports_no_send() -> None:
    """Jev 置信度过低时如实告知，且不发送图片"""
    from nonebot_plugin_chat.utils import jev_judge
    from nonebot_plugin_chat.utils.tools import sticker as sticker_mod

    tools = _make_tools()
    tools.manager.search_sticker.return_value = [_make_sticker(3)]

    with (
        patch.object(jev_judge, "ask", AsyncMock(return_value={"pick": _choice("3", 0.2)})),
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
        patch.object(sticker_mod.UniMessage, "image") as image_mock,
    ):
        result = await tools.send_sticker("猫猫")

    assert result == "表情包判定的置信度过低（20%），本次没有发送表情包"
    image_mock.assert_not_called()


async def test_send_sticker_judge_failure_reports_no_send() -> None:
    """Jev 不可用时如实告知，且不发送图片"""
    from nonebot_plugin_chat.utils import jev_judge
    from nonebot_plugin_chat.utils.tools import sticker as sticker_mod

    tools = _make_tools()
    tools.manager.search_sticker.return_value = [_make_sticker(3)]

    with (
        patch.object(jev_judge, "ask", AsyncMock(side_effect=RuntimeError("no key"))),
        patch("nonebot_plugin_chat.utils.tools.sticker.lang.text", _fake_lang_text),
        patch.object(sticker_mod.UniMessage, "image") as image_mock,
    ):
        result = await tools.send_sticker("猫猫")

    assert result == "表情包判定暂时不可用，本次没有发送表情包"
    image_mock.assert_not_called()
