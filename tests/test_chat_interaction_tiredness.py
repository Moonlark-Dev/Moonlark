"""困倦度提示的回归测试。

需求：四份互动规则（群聊 standard / passionate / silent、私聊）都必须带上公共的
``interaction_tiredness.md.jinja``——说明困倦度是 Moonlark 自己按生物钟产生的状态，
并允许在困倦度较高时用打哈欠、准备睡觉等动作把困意表现出来；include 必须被真实展开。
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
@pytest.mark.parametrize(
    ("is_group_session", "interaction_mode"),
    [
        (True, "standard"),
        (True, "passionate"),
        (True, "silent"),
        (False, "standard"),
    ],
)
async def test_tiredness_hint_included_in_every_interaction_mode(is_group_session: bool, interaction_mode: str) -> None:
    text = await _render_chat_prompt(
        is_group_session=is_group_session,
        is_private=not is_group_session,
        interaction_mode=interaction_mode,
    )

    assert "## 关于困倦度" in text
    # 困倦度是 Moonlark 自己按生物钟产生的，不是群友的、也不是心情
    assert "生物钟" in text
    assert "不是群友的，也不是心情值" in text
    # 困倦度较高时可以用动作表现困意
    assert "打哈欠" in text
    assert "准备去睡觉" in text

    # include 必须真实展开，不能把模板标签漏给模型
    assert "{% include" not in text
    assert "interaction_tiredness.md.jinja" not in text
