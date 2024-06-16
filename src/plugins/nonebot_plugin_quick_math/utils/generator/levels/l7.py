from nonebot.log import logger
from random import randint, choice
from sympy import Symbol, diff, limit, latex

from ....types import Question
from ....__main__ import lang

async def generate_limit_question(user_id: str):
    x = Symbol("x")
    f = choice(
        [x**2 + 3 * x - 2, x**3 - 2 * x + 1, x**4 - 4 * x**3 + 5 * x**2 + 2 * x - 1]
    )
    a = randint(-10, 10)
    _limit = limit(f, x, a)
    question = await lang.text("question.l7-limit", user_id, a, latex(f))
    answer = latex(_limit)
    return question, answer



async def generate_question(user_id: str) -> Question:
    x = Symbol("x")
    a = randint(1, 10)
    b = randint(1, 10)
    c = randint(1, 10)
    d = randint(1, 10)
    f = a * x**3 + b * x**2 + c * x + d
    match randint(1, 4):
        case 1:
            answer = str(diff(f, x)).replace(" ", "")
            question = await lang.text("question.l7-diff", user_id, latex(f))
        case 2:
            answer = str(diff(diff(f, x), x)).replace(" ", "")
            question = await lang.text("question.l7-diff-diff", user_id, latex(f))
        case 3:
            f = a * x**2 + b * x + c
            answer = str(object=diff(f, x)).replace(" ", "")
            question = await lang.text("question.l7-diff", user_id, latex(f))
        case _:
            question, answer = await generate_limit_question(user_id)
    logger.debug(answer)
    return {"question": question, "answer": answer.replace("*", "").replace("+", "\\+")}