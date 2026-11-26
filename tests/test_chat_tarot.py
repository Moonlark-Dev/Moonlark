"""塔罗牌工具的牌库、牌阵与返回格式测试"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAT_LANG_PATH = REPO_ROOT / "src" / "lang" / "zh_hans" / "chat.yaml"


def _get_tarot_lang() -> dict:
    with Path(CHAT_LANG_PATH).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_get_text():
    """用真实的 zh_hans 模板渲染，避免测试里再抄一份文案"""
    lang = _get_tarot_lang()

    def lookup(key: str):
        node = lang
        for part in key.split("."):
            node = node[part]
        return node

    async def get_text(key: str, *args) -> str:
        # 与 LarkLang 一致：去掉块标量末尾的换行
        return lookup(key).format(*args).rstrip("\n")

    return get_text


def test_tarot_deck_has_78_unique_cards() -> None:
    """整副塔罗牌应为 22 张大阿卡纳 + 56 张小阿卡纳，且牌名不重复"""
    from nonebot_plugin_chat.utils.tools.tarot import TAROT_CARDS

    assert len(TAROT_CARDS) == 78
    assert len({card.name for card in TAROT_CARDS}) == 78
    assert len({card.english_name for card in TAROT_CARDS}) == 78
    for card in TAROT_CARDS:
        assert card.upright
        assert card.reversed


def test_spread_positions_have_expected_counts() -> None:
    """牌阵位置数必须与牌数一致"""
    from nonebot_plugin_chat.utils.tools.tarot import SPREADS

    assert len(SPREADS["single"]) == 1
    assert len(SPREADS["three"]) == 3
    assert len(SPREADS["celtic_cross"]) == 10


@pytest.mark.parametrize("spread", ["single", "three", "celtic_cross"])
def test_draw_cards_never_repeats(spread: str) -> None:
    """同一牌阵内不会抽到重复的牌"""
    from nonebot_plugin_chat.utils.tools.tarot import SPREADS, draw_cards

    count = len(SPREADS[spread])
    for _ in range(20):
        drawn = draw_cards(count)
        assert len(drawn) == count
        assert len({card.name for card, _ in drawn}) == count


@pytest.mark.parametrize("spread", ["single", "three", "celtic_cross"])
async def test_draw_tarot_keeps_question_and_lists_positions(spread: str) -> None:
    """问题参数原样返回，结果包含每个位置的牌、正逆位与含义"""
    from nonebot_plugin_chat.utils.tools.tarot import SPREADS, draw_tarot_cards

    # 花括号、换行、标点都不能被当成格式化模板或转义掉
    question = "我该不该辞职？{不是占位符}\n第二行：真的吗!"
    result = await draw_tarot_cards(spread, question, _make_get_text())

    assert f"问题：{question}" in result
    assert result.count("含义：") == len(SPREADS[spread])
    for position in SPREADS[spread]:
        assert position.name in result
    assert "正位" in result or "逆位" in result


async def test_draw_tarot_accepts_chinese_spread_alias() -> None:
    """模型把牌型写成中文时也能正常抽取"""
    from nonebot_plugin_chat.utils.tools.tarot import draw_tarot_cards

    result = await draw_tarot_cards("三张", "测试问题", _make_get_text())

    assert "问题：测试问题" in result
    assert "三张牌（过去 / 现在 / 未来）" in result
    assert result.count("含义：") == 3


async def test_draw_tarot_reports_invalid_spread_and_question() -> None:
    """未知牌型返回可选牌型，并保留原问题"""
    from nonebot_plugin_chat.utils.tools.tarot import draw_tarot_cards

    result = await draw_tarot_cards("unknown", "原样返回的问题", _make_get_text())

    assert "未知的牌型「unknown」" in result
    assert "single" in result
    assert "three" in result
    assert "celtic_cross" in result
    assert "问题：原样返回的问题" in result
