import random
from ....types import Question
from ....__main__ import lang
from .options import build_options, int_distractors


async def generate_question(user_id: str) -> Question:
    a = random.randint(-100, 100)
    b = random.randint(-100, 100)
    answer = a + b
    if b <= 0:
        b *= -1
        question = await lang.text("question.l2-1", user_id, a, b)
    else:
        question = await lang.text("question.l2-2", user_id, a, b)

    async def verify(string: str) -> bool:
        return string.strip() == str(answer)

    return {
        "question": question,
        "answer": verify,
        "options": build_options(answer, int_distractors(answer)),
    }
