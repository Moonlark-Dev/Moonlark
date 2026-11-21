"""《缩略》纯本地答案判定：区分命中缩略词、误答原词全称与普通错误。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .store import is_exact_match, parse_breakdown

if TYPE_CHECKING:
    from .types import GeneratedQuestion

JudgeOutcome = Literal["correct", "full_word", "wrong"]


def judge_guess(guess: str, question: GeneratedQuestion) -> JudgeOutcome:
    """在本地判定玩家输入：命中预设缩略词返回 ``correct``，误填原词全称返回 ``full_word``，其余返回 ``wrong``。"""
    stripped = guess.strip()
    if not stripped:
        return "wrong"
    if any(is_exact_match(stripped, ans) for ans in question.answers):
        return "correct"
    if is_exact_match(stripped, question.full_word):
        return "full_word"
    parsed = parse_breakdown(question.breakdown)
    if parsed is not None and is_exact_match(stripped, parsed[0]):
        return "full_word"
    return "wrong"
