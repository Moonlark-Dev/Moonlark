"""说话腔调规则的回归测试。

需求：四份互动规则（群聊 standard / passionate / silent、私聊）都必须带上公共的
``speech_style.md.jinja``——单字短句、盖章式肯定、语气词单调这三类问题的措辞约束要
在所有互动模式下生效，且 include 必须被真实展开（不能把 Jinja 标签漏进提示词）。
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
async def test_speech_style_included_in_every_interaction_mode(is_group_session: bool, interaction_mode: str) -> None:
    text = await _render_chat_prompt(
        is_group_session=is_group_session,
        is_private=not is_group_session,
        interaction_mode=interaction_mode,
    )

    # 五条腔调规则都要在（按标题匹配，避免措辞微调就误报）
    assert "## 说话腔调" in text
    assert "话要说完整，不要用单字打发人" in text
    assert "不要盖章式地表示肯定" in text
    assert "语气词要错开" in text
    assert "不要背定义，用具体画面说话" in text
    assert "精简的是信息，不是语气" in text

    # include 必须真实展开，不能把模板标签漏给模型
    assert "{% include" not in text
    assert "speech_style.md.jinja" not in text


@pytest.mark.asyncio
async def test_compress_rule_points_to_speech_style() -> None:
    """发言精简原则必须补上「精简的是信息量，不是把句子砍成词」的说明"""
    text = await _render_chat_prompt()

    assert "精简的是信息量，不是把句子砍成一个个词" in text


@pytest.mark.asyncio
async def test_speech_style_keeps_the_neko_verbal_tics() -> None:
    """腔调规则是对人设的细化：喵的口癖要保留，不能压成「减少喵」"""
    text = await _render_chat_prompt()

    assert "这一条不是让你少用喵" in text


@pytest.mark.asyncio
async def test_group_prompt_tells_model_particles_are_free() -> None:
    """群聊 Token 规则必须说明语气词不收费，并给出被 @ 时的额度"""
    text = await _render_chat_prompt(is_group_session=True, is_private=False, interaction_mode="standard")

    assert "每 8 个有效字消耗 1 Token" in text
    assert "语气词和标点不收费" in text
    assert "首条消息即使 Token 为负也会放行" in text
