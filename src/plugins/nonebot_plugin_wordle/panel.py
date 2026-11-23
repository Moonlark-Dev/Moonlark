"""WORDLE 作答面板的渲染工具。

作答记录不再渲染成图片：QQ 官方机器人使用带 LaTeX 色块的 Markdown 面板，
其他适配器（如 OneBot V11）没有 Markdown 与 LaTeX，改为等价的纯文本色块面板。
本模块只放与 NoneBot 无关的纯函数，方便单元测试。
"""

from collections import Counter

from nonebot_plugin_larkutils.command import get_command_prefix

MAX_ATTEMPTS = 6
QUIT_KEYWORD = "q"

# 格子状态 -> (LaTeX 背景色, LaTeX 前景色)
TILE_COLORS: dict[str, tuple[str, str]] = {
    "correct": ("green", "black"),
    "present": ("yellow", "black"),
    "absent": ("gray", "white"),
    # 未作答的占位格：字母与底色同色，只剩一个与字母等宽的灰色块
    "empty": ("gray", "gray"),
}

# 纯文本面板使用的色块；未作答的格子与「字母不存在」共用白色方块
TILE_EMOJI: dict[str, str] = {
    "correct": "🟩",
    "present": "🟨",
    "absent": "⬜",
    "empty": "⬜",
}


def normalize_guess(text: str) -> str:
    """把玩家输入规范成实际作答的单词：去掉首尾空白与指令前缀并转为小写。

    QQ 官方机器人的「作答」按钮点击后会在输入框预填指令前缀，因此玩家实际发出的
    消息可能是 ``<前缀>Crane``；等待器需要按 ``crane`` 判断它是否是合法单词。
    """
    guess = text.strip()
    prefix = get_command_prefix()
    if prefix and guess.startswith(prefix):
        guess = guess[len(prefix) :].strip()
    return guess.lower()


def evaluate_guess(guess: str, answer: str) -> list[str]:
    """计算每个字母的状态（correct/present/absent），重复字母按 Wordle 的规则计数。"""
    remaining = Counter(answer)
    states: list[str] = ["absent"] * len(guess)
    for index, letter in enumerate(guess):
        if index < len(answer) and letter == answer[index]:
            states[index] = "correct"
            remaining[letter] -= 1
    for index, letter in enumerate(guess):
        if states[index] == "correct":
            continue
        if remaining[letter] > 0:
            states[index] = "present"
            remaining[letter] -= 1
    return states


def latex_tile(letter: str, state: str) -> str:
    """生成单个 LaTeX 色块，例如 ``\\colorbox{green}{\\textcolor{black}{\\text{C}}}``。"""
    background, foreground = TILE_COLORS[state]
    return rf"\colorbox{{{background}}}{{\textcolor{{{foreground}}}{{\text{{{letter.upper()}}}}}}}"


def build_latex_row(letters: str, answer: str, length: int) -> str:
    """把一行作答渲染为一个 LaTeX 公式；``letters`` 为空时渲染未作答的占位行。"""
    if letters:
        tiles = [latex_tile(letter, state) for letter, state in zip(letters, evaluate_guess(letters, answer))]
    else:
        tiles = [latex_tile("A", "empty") for _ in range(length)]
    return "$" + "".join(tiles) + "$"


def build_plain_row(letters: str, answer: str, length: int) -> str:
    """把一行作答渲染为纯文本：每个字母后跟一个色块，例如 ``C🟩 R🟨 A⬜ N⬜ E⬜``。"""
    if not letters:
        return TILE_EMOJI["empty"] * length
    return " ".join(
        f"{letter.upper()}{TILE_EMOJI[state]}" for letter, state in zip(letters, evaluate_guess(letters, answer))
    )
