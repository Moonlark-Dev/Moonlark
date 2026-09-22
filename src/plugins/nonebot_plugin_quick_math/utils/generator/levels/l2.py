import random
from ....types import Question
from ....__main__ import lang
from .options import build_choices, int_distractors


async def generate_question(user_id: str) -> Question:
    a = random.randint(-100, 100)
    b = random.randint(-100, 100)
    answer = a + b
    if b <= 0:
        b *= -1
        question = await lang.text("question.l2-1", user_id, a, b)
    else:
        question = await lang.text("question.l2-2", user_id, a, b)

    options, answer_letter = build_choices(answer, int_distractors(answer))
    return {
        "question": question,
        "answer": answer_letter,
        "options": options,
    }
