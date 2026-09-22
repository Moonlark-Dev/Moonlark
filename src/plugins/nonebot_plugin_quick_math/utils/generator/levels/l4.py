import random
from ....types import Question
from ....__main__ import lang
from .options import build_choices, int_distractors


async def generate_question(user_id: str) -> Question:
    a = random.randint(-5, 10)
    b = random.randint(1, 10)
    c = random.randint(1, 50)
    question_type = random.randint(1, 6)
    question = await lang.text(f"question.l4-{question_type}", user_id, a, b, c)
    match question_type:
        case 1:
            answer = (a + b) ** 2
        case 2:
            answer = (a - b) ** 2
        case 3:
            answer = (a + b) ** 2 + c
        case 4:
            answer = (a + b) ** 2 - c
        case 5:
            answer = (a - b) ** 2 + c
        case 6:
            answer = (a - b) ** 2 - c

    options, answer_letter = build_choices(answer, int_distractors(answer))
    return {
        "question": question,
        "answer": answer_letter,
        "options": options,
    }
