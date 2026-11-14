"""Check Note 的上下文测试：工具调用结果必须一起交给判断模型

Moonlark 经常先 ``browse_webpage`` 查到内容、再根据它写笔记。如果 Check Note 只看
聊天记录，判断模型没有依据，会以「无法验证」为由拒绝这条笔记。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch


def _call(name: str, params: dict[str, Any], result: Any = None) -> dict[str, Any]:
    return {"call_id": f"call_{name}", "name": name, "params": params, "result": result, "time": "2026-11-15T01:00:00"}


def test_serialize_tool_calls_keeps_name_params_and_result() -> None:
    from nonebot_plugin_chat.utils.note_manager import serialize_tool_calls

    text = serialize_tool_calls(
        [
            _call(
                "browse_webpage",
                {"url": "https://example.com/a"},
                "网页标题：示例\n正文：今年诺贝尔文学奖得主是 X。",
            ),
        ],
    )

    assert "### browse_webpage" in text
    assert "https://example.com/a" in text
    assert "今年诺贝尔文学奖得主是 X" in text


def test_serialize_tool_calls_skips_call_without_result() -> None:
    """正在执行的 push_note 自己还没有结果，不能被写进判断上下文"""
    from nonebot_plugin_chat.utils.note_manager import serialize_tool_calls

    text = serialize_tool_calls(
        [
            _call("browse_webpage", {"url": "https://example.com"}, "页面内容"),
            _call("push_note", {"text": "笔记内容"}),
        ],
    )

    assert "browse_webpage" in text
    assert "push_note" not in text


def test_serialize_tool_calls_truncates_long_inputs() -> None:
    from nonebot_plugin_chat.utils.note_manager import (
        NOTE_CHECK_TOOL_PARAM_LIMIT,
        NOTE_CHECK_TOOL_RESULT_LIMIT,
        serialize_tool_calls,
    )

    long_result = "正" * (NOTE_CHECK_TOOL_RESULT_LIMIT + 200)
    long_url = "https://example.com/" + "a" * (NOTE_CHECK_TOOL_PARAM_LIMIT + 100)

    text = serialize_tool_calls([_call("browse_webpage", {"url": long_url}, long_result)])

    assert long_result not in text
    assert long_url not in text
    assert "…" in text
    assert len(text) < NOTE_CHECK_TOOL_RESULT_LIMIT + NOTE_CHECK_TOOL_PARAM_LIMIT + 100


def test_serialize_tool_calls_handles_non_string_result() -> None:
    from nonebot_plugin_chat.utils.note_manager import serialize_tool_calls

    text = serialize_tool_calls([_call("query_gift", {"name": "礼物"}, {"count": 3})])

    assert '"count": 3' in text


def test_serialize_tool_calls_handles_empty_result_and_no_calls() -> None:
    from nonebot_plugin_chat.utils.note_manager import serialize_tool_calls

    assert serialize_tool_calls([]) == ""
    assert "(无返回内容)" in serialize_tool_calls([_call("send_reaction", {"emoji": "1"}, "")])


async def test_check_note_passes_tool_calls_to_prompt() -> None:
    """check_note 把会话的工具调用记录一起交给模板"""
    from nonebot_plugin_chat.utils import note_manager as note_manager_module

    tool_calls = [_call("browse_webpage", {"url": "https://example.com"}, "网页正文：答案在这里")]
    session = SimpleNamespace(
        get_cached_messages_string=AsyncMock(return_value="[10:00:00][小明]: 帮我查一下"),
        tool_calls_history=tool_calls,
    )
    captured: dict[str, Any] = {}

    async def fake_get_messages(prefix: str, **kwargs: Any) -> list[Any]:
        captured["prefix"] = prefix
        captured["kwargs"] = kwargs
        return []

    with (
        patch.object(note_manager_module, "get_messages", side_effect=fake_get_messages),
        patch.object(note_manager_module, "fetch_json", AsyncMock(return_value={"create": False, "comment": "no"})),
    ):
        result = await note_manager_module.check_note(session, "关键词", "笔记内容", 24.0)

    assert result["create"] is False
    assert captured["prefix"] == "check_note"
    assert captured["kwargs"]["messages"] == "[10:00:00][小明]: 帮我查一下"
    assert "网页正文：答案在这里" in captured["kwargs"]["tool_calls"]
    assert captured["kwargs"]["keywords"] == "关键词"
    assert captured["kwargs"]["content"] == "笔记内容"


async def test_check_note_prompt_renders_tool_section() -> None:
    """模板在有工具调用时给出独立小节，没有时不留空标题"""
    from nonebot_plugin_chat.utils.note_manager import serialize_tool_calls
    from nonebot_plugin_openai.utils.message import get_messages

    with_tools = await get_messages(
        "check_note",
        messages="[10:00:00][小明]: 帮我查一下",
        tool_calls=serialize_tool_calls([_call("browse_webpage", {"url": "https://example.com"}, "答案是 X")]),
        keywords="示例 答案",
        content="示例网站的答案是 X",
        expire_time="2026-11-16T10:00:00",
    )
    without_tools = await get_messages(
        "check_note",
        messages="[10:00:00][小明]: 你好",
        tool_calls="",
        keywords="",
        content="小明今天很开心",
        expire_time="2026-11-16T10:00:00",
    )

    system_prompt, user_prompt = with_tools
    assert "工具调用记录" in user_prompt["content"]
    assert "答案是 X" in user_prompt["content"]
    assert "调用工具" in system_prompt["content"]

    assert "工具调用记录" not in without_tools[1]["content"]
    assert without_tools[1]["content"].strip().startswith("## 消息记录")
