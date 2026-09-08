"""选择题选项生成工具。

各等级题目生成器在已知标准答案的前提下，生成若干干扰项，
并由 :func:`build_options` 去重、剔除与正确答案相同的项后乱序返回。
QQ 官方机器人下这些选项会渲染为可点击的键盘按钮。
"""

import random
from fractions import Fraction
from typing import Iterable

from ....config import config


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


def build_options(correct: str, distractors: Iterable[str]) -> list[str]:
    """将正确答案与干扰项合并、去重并乱序，返回选项列表。

    选项总数受 ``config.qm_choice_options``（干扰项数量）控制；
    配置为 0 时返回空列表，表示不启用选择题。
    """
    if config.qm_choice_options <= 0:
        return []
    options = [str(correct)]
    for distractor in distractors:
        text = str(distractor)
        if text != str(correct) and text not in options:
            options.append(text)
        if len(options) > config.qm_choice_options:
            break
    random.shuffle(options)
    return options
