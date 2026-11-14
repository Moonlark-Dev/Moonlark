"""Chat 的 Gemini 特性：图片被拦截后的 Image Describe 替换、System Prompt 双图片格式"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

PNG_BYTES = b"\x89PNG-blocked-image"
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")


def _make_handler(context: Any, text: Any) -> Any:
    """构造调用 ``MessageQueue.handle_blocked_images`` 所需的 self"""
    return SimpleNamespace(
        context=context,
        processor=SimpleNamespace(session=SimpleNamespace(text=text, lang_str="zh_hans")),
    )


async def _fake_text(key: str, *args: Any, **_kwargs: Any) -> str:
    if key == "parser.image_with_id":
        return f"[图片({args[0]}): {args[1]}]"
    if key == "parser.image_failed":
        return "[图片: 获取失败]"
    raise AssertionError(f"未预期的语言键: {key}")


@pytest.fixture
def describe_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """替换掉真正调用 Image Describe 模型的函数"""
    from nonebot_plugin_chat.core import message as message_module

    spy = AsyncMock(return_value=("一只趴在键盘上的猫", "img_1"))
    monkeypatch.setattr(message_module, "request_describe_image", spy)
    return spy


async def test_new_message_images_are_replaced(describe_spy: AsyncMock) -> None:
    """优先替换本轮新加消息里的图片，并同步写回 chat context"""
    from nonebot_plugin_chat.core.message import MessageQueue

    context = SimpleNamespace(replace_llm_message_content=AsyncMock(return_value=True))
    messages = [
        {"role": "system", "content": "系统"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这是什么"},
                {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
            ],
        },
    ]
    fetcher_session = SimpleNamespace(messages=messages, request_start_index=2)

    result = await MessageQueue.handle_blocked_images(_make_handler(context, _fake_text), fetcher_session)

    assert result is True
    describe_spy.assert_awaited_once_with(PNG_BYTES, "zh_hans")
    new_content = messages[1]["content"]
    assert new_content[0] == {"type": "text", "text": "这是什么"}
    assert new_content[1] == {"type": "text", "text": "[图片(img_1): 一只趴在键盘上的猫]"}
    context.replace_llm_message_content.assert_awaited_once_with(1, new_content)


async def test_falls_back_to_history_images(describe_spy: AsyncMock) -> None:
    """本轮没有新图片时回退到替换历史图片，否则每次请求都会在同一张图上被拦截"""
    from nonebot_plugin_chat.core.message import MessageQueue

    context = SimpleNamespace(replace_llm_message_content=AsyncMock(return_value=True))
    messages = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": PNG_DATA_URL}}]},
        {"role": "assistant", "content": "看到了"},
        {"role": "user", "content": "继续"},
    ]
    fetcher_session = SimpleNamespace(messages=messages, request_start_index=len(messages))

    result = await MessageQueue.handle_blocked_images(_make_handler(context, _fake_text), fetcher_session)

    assert result is True
    assert messages[0]["content"] == [{"type": "text", "text": "[图片(img_1): 一只趴在键盘上的猫]"}]
    context.replace_llm_message_content.assert_awaited_once()


async def test_no_images_returns_false() -> None:
    """没有任何图片时不重试"""
    from nonebot_plugin_chat.core.message import MessageQueue

    context = SimpleNamespace(replace_llm_message_content=AsyncMock())
    messages = [{"role": "user", "content": [{"type": "text", "text": "只有文字"}]}]
    fetcher_session = SimpleNamespace(messages=messages, request_start_index=0)

    assert await MessageQueue.handle_blocked_images(_make_handler(context, _fake_text), fetcher_session) is False
    context.replace_llm_message_content.assert_not_awaited()


async def test_undecodable_image_is_replaced_with_failure_placeholder() -> None:
    """data URL 无法解码时也要把图片换掉，避免同一张图反复触发拦截"""
    from nonebot_plugin_chat.core.message import MessageQueue

    context = SimpleNamespace(replace_llm_message_content=AsyncMock(return_value=True))
    messages = [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,!!!"}}],
        }
    ]
    fetcher_session = SimpleNamespace(messages=messages, request_start_index=0)

    result = await MessageQueue.handle_blocked_images(_make_handler(context, _fake_text), fetcher_session)

    assert result is True
    assert messages[0]["content"] == [{"type": "text", "text": "[图片: 获取失败]"}]


async def test_system_prompt_includes_dual_image_format_in_gemini_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini 模式下 System Prompt 同时声明内嵌图片与描述图片两种格式"""
    from nonebot_plugin_chat.core import processor as processor_module

    captured: dict[str, Any] = {}

    async def fake_get_message(_role: str, _name: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"role": "system", "content": "系统提示"}

    async def fake_provider() -> str:
        return "gemini"

    monkeypatch.setattr(processor_module, "get_message", fake_get_message)
    monkeypatch.setattr(processor_module, "get_model_provider", fake_provider)
    processor = SimpleNamespace(
        ENABLE_EMBEDDED_IMAGE=True,
        session=SimpleNamespace(get_session_type=lambda: "group"),
        get_interaction_mode=AsyncMock(return_value="standard"),
        is_intimate_interaction_prompt_beta_enabled=AsyncMock(return_value=False),
    )

    message = await processor_module.MessageProcessor.generate_system_prompt(processor)

    assert message == {"role": "system", "content": "系统提示"}
    assert captured["image_placeholder"] is True
    assert captured["dual_image_format"] is True


async def test_system_prompt_single_image_format_in_openai_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI 模式下保持原有的单一图片格式定义"""
    from nonebot_plugin_chat.core import processor as processor_module

    captured: dict[str, Any] = {}

    async def fake_get_message(_role: str, _name: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"role": "system", "content": "系统提示"}

    async def fake_provider() -> str:
        return "openai"

    monkeypatch.setattr(processor_module, "get_message", fake_get_message)
    monkeypatch.setattr(processor_module, "get_model_provider", fake_provider)
    processor = SimpleNamespace(
        ENABLE_EMBEDDED_IMAGE=True,
        session=SimpleNamespace(get_session_type=lambda: "group"),
        get_interaction_mode=AsyncMock(return_value="standard"),
        is_intimate_interaction_prompt_beta_enabled=AsyncMock(return_value=False),
    )

    await processor_module.MessageProcessor.generate_system_prompt(processor)

    assert captured["dual_image_format"] is False


def _render_chat_prompt(**kwargs: Any) -> str:
    from jinja2 import Environment, FileSystemLoader

    environment = Environment(
        loader=FileSystemLoader("src/prompt"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    defaults = {
        "image_placeholder": True,
        "dual_image_format": False,
        "is_group_session": True,
        "is_private": False,
        "session_nickname": None,
        "interaction_mode": "standard",
        "intimate_interaction_prompt_beta": False,
    }
    defaults.update(kwargs)
    return environment.get_template("chat.md.jinja").render(**defaults)


def test_chat_prompt_defines_both_image_formats_when_dual() -> None:
    """System Prompt 模板：dual 模式包含两种图片格式，普通模式仍然只有一种"""
    dual = _render_chat_prompt(dual_image_format=True)
    assert "`[图片(图片ID)]`" in dual
    assert "`[图片(图片ID): 图片描述]`" in dual

    single = _render_chat_prompt(dual_image_format=False)
    assert "`[图片(图片ID)]`" in single
    assert "`[图片(图片ID): 图片描述]`" not in single
