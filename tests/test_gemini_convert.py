"""Gemini 插件：OpenAI 风格消息 -> Gemini Content 的转换测试"""

from __future__ import annotations

import base64
import json

import pytest

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-data"
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")


def test_system_messages_become_system_instruction() -> None:
    """多条 system 消息合并进 system_instruction，不进 contents"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    system_instruction, contents = convert_messages(
        [
            {"role": "system", "content": "你是 Moonlark"},
            {"role": "system", "content": "保持简短"},
            {"role": "user", "content": "你好"},
        ]
    )

    assert system_instruction == "你是 Moonlark\n\n保持简短"
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "你好"


def test_user_image_part_is_converted_to_inline_data() -> None:
    """image_url 内容块转换成 inline_data（Gemini 只接受内联图片）"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    _, contents = convert_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "[图片(img_1)]"},
                    {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
                ],
            }
        ]
    )

    parts = contents[0].parts
    assert parts[0].text == "[图片(img_1)]"
    assert parts[1].inline_data is not None
    assert parts[1].inline_data.mime_type == "image/png"
    assert parts[1].inline_data.data == PNG_BYTES


def test_remote_image_url_is_skipped() -> None:
    """非 data URL 的图片无法交给 Gemini，直接跳过而不是让整轮请求失败"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    _, contents = convert_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看这张图"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                ],
            }
        ]
    )

    assert [part.text for part in contents[0].parts] == ["看这张图"]


def test_tool_call_and_response_are_converted() -> None:
    """assistant 的 tool_calls 转成 function_call，tool 消息转成 function_response 并带上函数名"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    _, contents = convert_messages(
        [
            {"role": "user", "content": "今天天气"},
            {
                "role": "assistant",
                "content": "我查一下",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": json.dumps({"city": "杭州"})},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "晴，25℃"},
        ]
    )

    assert [content.role for content in contents] == ["user", "model", "user"]
    function_call = contents[1].parts[1].function_call
    assert function_call is not None
    assert function_call.id == "call-1"
    assert function_call.name == "get_weather"
    assert function_call.args == {"city": "杭州"}

    function_response = contents[2].parts[0].function_response
    assert function_response is not None
    assert function_response.id == "call-1"
    assert function_response.name == "get_weather"
    assert function_response.response == {"result": "晴，25℃"}


def test_thought_signature_round_trip() -> None:
    """tool_calls 里的 thought_signature（base64）会被还原到 function_call part 上"""
    from nonebot_plugin_gemini.utils.convert import THOUGHT_SIGNATURE_KEY, convert_messages

    signature = b"signature-bytes"
    _, contents = convert_messages(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-9",
                        "type": "function",
                        "function": {"name": "ping", "arguments": "{}"},
                        THOUGHT_SIGNATURE_KEY: base64.b64encode(signature).decode("ascii"),
                    }
                ],
            }
        ]
    )

    part = contents[0].parts[0]
    assert part.thought_signature == signature


def test_consecutive_same_role_messages_are_merged() -> None:
    """相邻同角色消息合并成一个 Content（工具返回与随后的用户消息同属 user）"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    _, contents = convert_messages(
        [
            {"role": "user", "content": "第一条"},
            {"role": "user", "content": "第二条"},
            {"role": "assistant", "content": "回复"},
        ]
    )

    assert [content.role for content in contents] == ["user", "model"]
    assert [part.text for part in contents[0].parts] == ["第一条", "第二条"]


def test_empty_messages_are_dropped() -> None:
    """空 content 不会生成空 part / 空 Content"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    _, contents = convert_messages(
        [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": None},
            {"role": "user", "content": [{"type": "text", "text": ""}]},
        ]
    )

    assert contents == []


def test_malformed_tool_arguments_are_treated_as_empty() -> None:
    """工具调用参数不是合法 JSON 时按空参数处理"""
    from nonebot_plugin_gemini.utils.convert import convert_messages

    _, contents = convert_messages(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call-2", "type": "function", "function": {"name": "f", "arguments": "{oops"}},
                ],
            }
        ]
    )

    assert contents[0].parts[0].function_call.args == {}


def test_image_part_helpers() -> None:
    """图片块识别与 data URL 解码"""
    from nonebot_plugin_gemini.utils.convert import (
        decode_data_url,
        image_part_indices,
        is_image_part,
    )

    content = [
        {"type": "text", "text": "x"},
        {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
    ]
    assert is_image_part(content[1])
    assert not is_image_part(content[0])
    assert image_part_indices(content) == [1]
    assert image_part_indices("纯文本") == []
    assert decode_data_url(PNG_DATA_URL) == (PNG_BYTES, "image/png")
    assert decode_data_url("https://example.com/a.png") is None


def test_generate_function_list_builds_json_schema() -> None:
    """工具参数被转换成 Gemini 的 FunctionDeclaration（JSON Schema 形式）"""
    from nonebot_plugin_gemini.utils.functions import generate_function_list

    async def sample_tool(city: str, mode: str = "a") -> str:  # pragma: no cover - 仅用于取名
        return city

    tools = generate_function_list(
        {
            "sample_tool": {
                "func": sample_tool,
                "description": "查询天气",
                "parameters": {
                    "city": {"type": "string", "description": "城市名", "required": True},
                    "mode": {"type": "string", "description": "模式", "required": False, "enum": {"a", "b"}},
                },
            }
        }
    )

    assert len(tools) == 1
    declaration = tools[0].function_declarations[0]
    assert declaration.name == "sample_tool"
    assert declaration.description == "查询天气"
    schema = declaration.parameters_json_schema
    assert schema["type"] == "object"
    assert schema["required"] == ["city"]
    assert schema["properties"]["city"] == {"type": "string", "description": "城市名"}
    assert sorted(schema["properties"]["mode"]["enum"]) == ["a", "b"]


def test_generate_function_list_without_tools() -> None:
    """没有工具时返回空列表（上层据此跳过 tools 参数）"""
    from nonebot_plugin_gemini.utils.functions import generate_function_list

    assert generate_function_list({}) == []


@pytest.mark.parametrize(
    ("model", "effort", "levels", "budgets", "expected"),
    [
        # 默认不配置任何映射：不向模型传递 thinking 配置
        ("gemini-2.5-flash", "medium", {}, {}, None),
        # Gemini 3 使用 thinking_level
        ("gemini-3-pro-preview", "low", {"low": "LOW"}, {}, ("level", "LOW")),
        # 更早的模型使用 thinking_budget
        ("gemini-2.5-pro", "medium", {}, {"medium": 8192}, ("budget", 8192)),
        # 没有对应档位时同样不传
        ("gemini-2.5-pro", "high", {}, {"medium": 8192}, None),
    ],
)
def test_build_thinking_config(
    model: str,
    effort: str,
    levels: dict[str, str],
    budgets: dict[str, int],
    expected: object,
) -> None:
    """reasoning_effort 按模型版本映射到 thinking_level / thinking_budget"""
    from nonebot_plugin_gemini.utils import chat as gemini_chat

    gemini_chat.config.gemini_thinking_levels = levels
    gemini_chat.config.gemini_thinking_budgets = budgets
    try:
        thinking = gemini_chat.build_thinking_config(model, effort)
    finally:
        gemini_chat.config.gemini_thinking_levels = {}
        gemini_chat.config.gemini_thinking_budgets = {}

    if expected is None:
        assert thinking is None
    else:
        kind, value = expected
        assert thinking is not None
        if kind == "level":
            assert thinking.thinking_level is not None
            assert (
                str(
                    thinking.thinking_level.value
                    if hasattr(thinking.thinking_level, "value")
                    else thinking.thinking_level
                )
                == value
            )
        else:
            assert thinking.thinking_budget == value
