"""主动私聊开场策略提示词测试。

确保主动私聊事件提示词（``proactive_message.prompt``）提供灵活的开场策略
（轻寒暄、抛引子、小事直说、本轮点到为止、隔久回复顺聊），且不写死具体台词例句
以避免复读；同时确保决策提示词（``proactive_chat``）职责分离，只输出话题意图而非整段台词。
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
def test_proactive_message_prompt_contains_opening_strategies(language: str) -> None:
    """各语言主动私聊提示词包含三类开场策略与轮次约束，且不硬编码固定寒暄例句"""
    template = _load_proactive_prompt(language)
    assert template == _load_proactive_prompt("zh_hans")

    rendered = template.format("刚看完芙莉莲第12集想分享感想")

    assert "本次主动消息的主题为：刚看完芙莉莲第12集想分享感想" in rendered
    assert "结合时段与近况轻寒暄" in rendered
    assert "抛半句引子" in rendered
    assert "简短小事直接说" in rendered
    assert "本轮点到为止" in rendered
    assert "顺着对方当下的话聊" in rendered
    # 避免固定例句锚定导致每次复读同一句话
    assert "在吗" not in rendered
    assert "今天过得怎么样" not in rendered


async def test_proactive_chat_decision_prompt_separates_intent_from_script() -> None:
    """主动私聊决策模板只要求概括话题方向或原因，不预写具体台词"""
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
    assert "不要预写成具体台词或整段话" in system_content
    assert "想找对方聊的话题方向或原因" in user_content
    assert "在吗" not in system_content
