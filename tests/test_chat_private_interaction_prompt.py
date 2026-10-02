"""私聊互动规则模板的回归测试。

需求：私聊恒定使用 ``interaction_private.md.jinja``（不受群聊 interaction_mode 影响），
群聊仍需按 passionate / silent / standard 正常选择；私聊模板允许用括号简短描述动作，
并要求对每一条消息都作出回应。
"""

import pytest


async def _render_chat_prompt(**overrides: object) -> str:
    """渲染 chat.md.jinja（插件导入必须在函数内部，见 tests/conftest.py）"""
    from nonebot_plugin_openai.utils.message import get_message_text

    kwargs: dict[str, object] = {
        "image_placeholder": True,
        "is_group_session": False,
        "is_private": True,
        "session_nickname": "小明",
        "interaction_mode": "standard",
    }
    kwargs.update(overrides)
    return await get_message_text("chat.md.jinja", **kwargs)


@pytest.mark.asyncio
async def test_private_session_uses_private_interaction_prompt() -> None:
    """私聊必须加载私聊专用互动规则，而不是任何群聊模式"""
    text = await _render_chat_prompt()

    assert "当前处于「私聊」场景" in text
    assert "热情模式" not in text
    assert "安静模式" not in text
    assert "以一只旁观的猫娘" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["passionate", "silent", "standard"])
async def test_private_session_ignores_group_interaction_mode(mode: str) -> None:
    """群聊互动模式不应影响私聊的互动规则选择"""
    text = await _render_chat_prompt(interaction_mode=mode)

    assert "当前处于「私聊」场景" in text
    assert "热情模式" not in text
    assert "安静模式" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "marker"),
    [
        ("passionate", "热情模式"),
        ("silent", "安静模式"),
        ("standard", "即使没有人@你"),
    ],
)
async def test_group_session_still_follows_interaction_mode(mode: str, marker: str) -> None:
    """群聊仍按 interaction_mode 选择互动规则"""
    text = await _render_chat_prompt(is_group_session=True, is_private=False, interaction_mode=mode)

    assert marker in text
    assert "当前处于「私聊」场景" not in text


@pytest.mark.asyncio
async def test_private_prompt_allows_bracketed_actions() -> None:
    """私聊模板放开括号动作描写，并删除原来的禁止条款"""
    text = await _render_chat_prompt()

    assert "允许用括号简短地描述自己的动作" in text
    assert "除非接到明确的要求，不要在消息中描述你的动作" not in text


@pytest.mark.asyncio
async def test_private_prompt_requires_reply_and_favorability_gate() -> None:
    """私聊模板要求必须回复，并保留好感度对亲密程度的限制"""
    text = await _render_chat_prompt()

    assert "每一条消息都必须得到回应" in text
    assert "私聊中可以更亲密，但程度依然由好感度决定" in text
    # 好感度细则需要被真实展开（include 生效）
    assert "好感度以整数形式表现" in text


@pytest.mark.asyncio
async def test_private_prompt_does_not_mention_group_only_tools() -> None:
    """私聊不消耗 Token，不应引导模型调用仅群聊可用的 apply_unlimited_tokens"""
    text = await _render_chat_prompt()

    assert "apply_unlimited_tokens" not in text
