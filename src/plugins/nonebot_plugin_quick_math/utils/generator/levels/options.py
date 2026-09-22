"""选择题选项生成工具。

QuickMath 的所有题目都是选择题：各等级题目生成器在已知标准答案的前提下生成若干
干扰项，由 :func:`build_choices` 去重、剔除与正确答案相同的项后乱序，并返回正确
答案对应的选项字母。QQ 官方机器人下选项渲染为可点击的键盘按钮，其余适配器则把
选项随题目一起渲染进图片，用户同样回复字母作答。
"""

import random
from fractions import Fraction
from typing import Iterable

from ....config import config

# 选项字母表：第 index 个选项对应 OPTION_LETTERS[index]
OPTION_LETTERS = "ABCDEFGHIJKL"


def _distractor_limit() -> int:
    """返回干扰项数量上限。

    选项必须始终存在（否则题目无法作答），因此即使 ``config.qm_choice_options``
    被配置为 0 或负数，也至少生成 1 个干扰项；同时不超过字母表长度。
    """
    return min(max(1, config.qm_choice_options), len(OPTION_LETTERS) - 1)


def int_distractors(answer: int, count: int = 3) -> list[str]:
    """以整数答案为中心生成 count 个不同的干扰项（字符串形式）。"""
    offsets = [1, -1, 2, -2, 10, -10, 100, -100, 1000, -1000]
    seen: set[int] = set()
    distractors: list[str] = []
    for offset in offsets:
        if len(distractors) >= count:
            break
        value = answer + offset
        if value != answer and value not in seen:
            seen.add(value)
            distractors.append(str(value))
    return distractors


def fraction_distractors(answer: Fraction, count: int = 3) -> list[str]:
    """以分数答案为中心生成 count 个不同的干扰项（分数/小数形式）。"""
    deltas: list[Fraction] = [
        Fraction(1),
        Fraction(-1),
        Fraction(2),
        Fraction(-2),
        Fraction(1, 2),
        Fraction(-1, 2),
        Fraction(10),
        Fraction(-10),
    ]
    seen = {str(answer)}
    distractors: list[str] = []
    for delta in deltas:
        if len(distractors) >= count:
            break
        value = answer + delta
        if (text := str(value)) not in seen:
            seen.add(text)
            distractors.append(text)
    return distractors


def build_choices(correct: str, distractors: Iterable[str]) -> tuple[list[str], str]:
    """合并正确答案与干扰项、去重乱序，返回 ``(选项列表, 正确选项字母)``。

    选项数量由 ``config.qm_choice_options``（干扰项数量）控制，至少 1 个干扰项，
    保证题目始终可作答。返回值中的字母即题目的 ``answer`` 字段，判题时只需把用户
    输入标准化后与字母比较。
    """
    correct_text = str(correct)
    options = [correct_text]
    limit = _distractor_limit()
    for distractor in distractors:
        text = str(distractor)
        if text != correct_text and text not in options:
            options.append(text)
        if len(options) > limit:
            break
    random.shuffle(options)
    return options, OPTION_LETTERS[options.index(correct_text)]
