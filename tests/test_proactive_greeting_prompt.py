"""主动私聊开场打招呼提示词测试。

确保主动私聊事件提示词（``proactive_message.prompt``）与主动私聊决策提示词
（``proactive_chat``）都引导 Moonlark 先简单打个招呼（如“在吗”或“今天过得怎么样”），
等对方回复后再自然引出话题，而不是一次性发送一大段消息。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

LANG_DIR = Path(__file__).resolve().parent.parent / "src" / "lang"
LANGS = ("zh_hans", "en_us", "zh_tw")


def _load_proactive_prompt(language: str) -> str:
    path = LANG_DIR / language / "chat.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["proactive_message"]["prompt"]


@pytest.mark.parametrize("language", LANGS)
def test_proactive_message_prompt_contains_greeting_tip(language: str) -> None:
    """各语言下的主动私聊提示词均包含先打招呼再引出内容的引导，且占位符可正常格式化"""
    template = _load_proactive_prompt(language)
    rendered = template.format("分享刚看到的有趣视频")

    assert "本次主动消息的主题为：分享刚看到的有趣视频" in rendered
    assert "打个招呼" in rendered
    assert "在吗" in rendered
    assert "今天过得怎么样" in rendered
    assert "等对方回复后再自然引出" in rendered


async def test_proactive_chat_decision_prompt_renders_greeting_guidance() -> None:
    """主动私聊决策模板可正常渲染，并提示可先打招呼再引出正题"""
    from nonebot_plugin_openai.utils.message import get_messages

    messages = await get_messages(
        "proactive_chat",
        friends="- 小明 (好感度: 120)",
        plan="下午看书",
        events="暂无事件",
        notes="暂无备忘录",
        recent_sends="暂无主动私聊发送记录。",
        current_time="2026-11-11 22:00:00",
    )

    assert len(messages) == 2
    system_content = messages[0]["content"]
    user_content = messages[1]["content"]
    assert isinstance(system_content, str)
    assert isinstance(user_content, str)
    assert "先简单打个招呼" in system_content
    assert "在吗" in system_content
    assert "今天过得怎么样" in system_content
    assert "想聊的话题或意图" in user_content
