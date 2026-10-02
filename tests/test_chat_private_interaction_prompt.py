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


@pytest.mark.asyncio
async def test_favorability_table_uses_private_wording_in_private_chat() -> None:
    """共享的 favorability.md.jinja 需按 is_private 换成一对一措辞"""
    text = await _render_chat_prompt()

    assert "私聊中对对方的称呼" in text
    assert "对方主动搭话时会回应" in text
    assert "对越界的亲密请求冷淡回避" in text
    assert "等）。会下意识维护对方。" in text

    # 群聊专属措辞不得出现在私聊提示词中
    assert "群聊中对他人的称呼" not in text
    assert "群内@会回应" not in text
    assert "这位群友" not in text
    assert "对私聊请求冷淡回避" not in text
    assert "在群内会下意识维护对方" not in text


@pytest.mark.asyncio
async def test_favorability_table_keeps_group_wording_in_group_chat() -> None:
    """群聊下好感度表必须保持原有措辞（避免私聊改动污染群聊提示词）"""
    text = await _render_chat_prompt(is_group_session=True, is_private=False, interaction_mode="standard")

    assert "群聊中对他人的称呼" in text
    assert "“你”“这位群友”指代" in text
    assert "对私聊请求冷淡回避" in text
    assert "群内@会回应" in text
    assert "在群内会下意识维护对方" in text

    assert "私聊中对对方的称呼" not in text
    assert "对方主动搭话时会回应" not in text
    assert "越界的亲密请求" not in text


@pytest.mark.asyncio
async def test_favorability_template_without_flag_keeps_group_wording() -> None:
    """favorability.md.jinja 还会被独立渲染（moonlark_main.get_friends），未传 is_private 时回退为群聊措辞，且不破坏表格结构"""
    from nonebot_plugin_openai.utils.message import get_message_text

    text = await get_message_text("favorability.md.jinja")

    assert "群聊中对他人的称呼" in text
    assert "私聊中对对方的称呼" not in text
    for tier in ("[0 - 5]", "[6 - 50]", "[51 - 150]", "[151 - 300]", "[301+]"):
        assert tier in text
    # 条件标签容易被 trim_blocks 吃掉换行，这里守住档位之间的空行
    assert "\n\n[6 - 50]" in text
    assert "\n\n[301+] 灵魂耦合" in text
