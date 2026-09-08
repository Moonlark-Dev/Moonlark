from nonebot.log import logger
from random import randint, choice
from typing import Any
from sympy import Symbol, diff, limit, latex

from .options import build_options
from .utils import get_verify_function
from ....types import Question
from ....__main__ import lang


def _diff_text(expr: Any, x: Symbol, order: int = 1) -> str:
    result = expr
    for _ in range(order):
        result = diff(result, x)
    return str(result).replace(" ", "")


async def generate_limit_question(user_id: str) -> tuple[str, str, list[str]]:
    x = Symbol("x")
    f = choice([x**2 + 3 * x - 2, x**3 - 2 * x + 1, x**4 - 4 * x**3 + 5 * x**2 + 2 * x - 1])
    a = randint(-10, 10)
    _limit = limit(f, x, a)
    question = await lang.text("question.l7-limit", user_id, a, latex(f))
    answer = latex(_limit)
    variants = [latex(limit(f + k, x, a)) for k in range(1, 7)]
    return question, answer, variants


async def generate_question(user_id: str) -> Question:
    x = Symbol("x")
    a = randint(1, 10)
    b = randint(1, 10)
    c = randint(1, 10)
    d = randint(1, 10)
    match randint(1, 4):
        case 1:
            f = a * x**3 + b * x**2 + c * x + d
            answer = _diff_text(f, x)
            question = await lang.text("question.l7-diff", user_id, latex(f))
            variants = [_diff_text((a + k) * x**3 + (b - k) * x**2 + c * x + d, x) for k in range(1, 7)]
        case 2:
            f = a * x**3 + b * x**2 + c * x + d
            answer = _diff_text(f, x, 2)
            question = await lang.text("question.l7-diff-diff", user_id, latex(f))
            variants = [_diff_text((a + k) * x**3 + (b - k) * x**2 + c * x + d, x, 2) for k in range(1, 7)]
        case 3:
            f = a * x**2 + b * x + c
            answer = _diff_text(f, x)
            question = await lang.text("question.l7-diff", user_id, latex(f))
            variants = [_diff_text((a + k) * x**2 + (b - k) * x + c, x) for k in range(1, 7)]
        case _:
            question, answer, variants = await generate_limit_question(user_id)
    logger.debug(answer)
    return {
        "question": question,
        "answer": get_verify_function(answer, user_id),
        "options": build_options(answer, variants),
    }
