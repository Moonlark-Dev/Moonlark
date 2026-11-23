"""WORDLE 作答面板的渲染测试。"""

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORDLE_LANG = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "wordle.yaml"


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


@pytest.fixture
def wordle_templates(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """按真实 wordle.yaml 渲染文案，避免占位符与调用参数不匹配被静默吞掉。"""
    from nonebot_plugin_larklang.__main__ import LangHelper, remove_trailing_blank_lines

    templates = _flatten(yaml.safe_load(_WORDLE_LANG.read_text(encoding="utf-8")))

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *args: object, **kwargs: object) -> str:
        return remove_trailing_blank_lines(templates[key].format(*args, __prefix__="/", **kwargs))

    monkeypatch.setattr(LangHelper, "text", fake_text)
    return templates


def test_evaluate_guess_all_correct():
    from nonebot_plugin_wordle.panel import evaluate_guess

    assert evaluate_guess("crane", "crane") == ["correct"] * 5


def test_evaluate_guess_duplicate_letters():
    from nonebot_plugin_wordle.panel import evaluate_guess

    # 答案里的 b 有两个：第一个 b 位置不对算 present，第二个 b 位置正确算 correct
    assert evaluate_guess("babes", "abbey") == ["present", "present", "correct", "correct", "absent"]
    # 猜测里的 l 比答案多，多出来的 l 不计入 present
    assert evaluate_guess("lllll", "hello") == ["absent", "absent", "correct", "correct", "absent"]


def test_build_latex_row_uses_colorboxes():
    from nonebot_plugin_wordle.panel import build_latex_row

    row = build_latex_row("crane", "crane", 5)
    assert row.startswith("$") and row.endswith("$")
    assert row.count(r"\colorbox{green}") == 5
    assert r"\textcolor{black}{\text{C}}" in row


def test_build_latex_row_pads_empty_row():
    from nonebot_plugin_wordle.panel import build_latex_row

    row = build_latex_row("", "crane", 5)
    assert row.count(r"\colorbox{gray}") == 5
    assert r"\textcolor{gray}" in row


def test_build_plain_row():
    from nonebot_plugin_wordle.panel import build_plain_row

    assert build_plain_row("crane", "crane", 5) == "C🟩 R🟩 A🟩 N🟩 E🟩"
    assert build_plain_row("", "crane", 5) == "⬜⬜⬜⬜⬜"


def test_normalize_guess_strips_prefix_and_whitespace():
    from nonebot_plugin_larkutils.command import get_command_prefix
    from nonebot_plugin_wordle.panel import normalize_guess

    prefix = get_command_prefix()
    assert normalize_guess(f"  {prefix}Crane ") == "crane"
    assert normalize_guess("crane") == "crane"


def test_build_board_pads_to_max_attempts():
    from nonebot_plugin_wordle import Wordle
    from nonebot_plugin_wordle.panel import MAX_ATTEMPTS, build_plain_row

    game = Wordle("crane", "user", "", "group", None, None)  # type: ignore[arg-type]
    game.history = [list("crane")]
    rows = game.build_board(build_plain_row)
    assert len(rows) == MAX_ATTEMPTS
    assert rows[0] == "C🟩 R🟩 A🟩 N🟩 E🟩"
    assert rows[1] == "⬜⬜⬜⬜⬜"

    # 获胜的那一次作答还没写进 history，通过 extra_guess 展示
    rows = game.build_board(build_plain_row, extra_guess="nacre")
    assert len(rows) == MAX_ATTEMPTS
    assert rows[1].startswith("N")


def _qq_bot() -> Any:
    from nonebot.adapters.qq import Bot as QQBot

    return object.__new__(QQBot)


async def _build_panel(bot: Any, history: list[str]) -> Any:
    from nonebot_plugin_wordle import Wordle

    game = Wordle("crane", "u", "", "g", bot, None)  # type: ignore[arg-type]
    game.history = [list(guess) for guess in history]
    return await game.build_panel()


async def test_qq_panel_uses_latex_markdown_and_buttons(wordle_templates):
    from nonebot_plugin_larkutils.command import get_command_prefix

    message = await _build_panel(_qq_bot(), ["nacre"])
    text = message[0].text
    assert text.startswith("### WORDLE · 5 个字母")
    assert "第 **2** / **6** 次尝试" in text
    # nacre 相对 crane：e 位置正确，其余四个字母存在但位置不对
    assert r"\colorbox{green}{\textcolor{black}{\text{E}}}" in text
    assert r"\colorbox{yellow}{\textcolor{black}{\text{N}}}" in text
    assert "🟩 位置正确" in text

    buttons = message[1].children
    assert [str(button.label) for button in buttons] == ["作答", "放弃"]
    assert buttons[0].flag == "input"
    assert buttons[0].text == get_command_prefix()
    assert buttons[1].flag == "enter"
    assert buttons[1].text == "q"


async def test_plain_panel_uses_emoji_board(wordle_templates):
    message = await _build_panel(None, ["nacre"])
    text = str(message)
    assert "WORDLE · 5 个字母" in text
    assert "第 2/6 次尝试" in text
    assert "N🟨 A🟨 C🟨 R🟨 E🟩" in text
    assert "⬜⬜⬜⬜⬜" in text
    assert "\\colorbox" not in text


async def test_qq_result_panel_shows_final_board(wordle_templates):
    from nonebot_plugin_wordle import Wordle

    game = Wordle("crane", "u", "", "g", _qq_bot(), None)  # type: ignore[arg-type]
    game.history = [list("nacre")]
    message = await game.build_result("回答正确！答案是:\n  crane (起重机)", extra_guess="crane")
    assert not isinstance(message, str)
    text = message[0].text
    assert text.count(r"\colorbox{green}") == 6  # nacre 的 e + 猜中的整行 crane
    assert "回答正确！" in text
