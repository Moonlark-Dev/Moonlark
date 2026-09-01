import random
from fractions import Fraction
from ....types import Question
from ....__main__ import lang
from .options import build_options, fraction_distractors, int_distractors


async def generate_question(user_id: str) -> Question:
    a = random.randint(-50, 50)
    b = random.randint(-50, 50)
    if b == 0:
        question_type = 1
    else:
        question_type = random.randint(1, 2)
    if b < 0:
        question_type += 2
    question = await lang.text(f"question.l3-{question_type}", user_id, a, b)
    match question_type:
        case 1 | 3:
            answer = a * b
            int_answer = True
        case _:
            answer = a / b
            int_answer = False
    if int_answer:
        answer_value: int = int(answer)
        distractors = int_distractors(answer_value)

        async def verify(string: str) -> bool:
            return string.strip() == str(answer_value)

    else:
        answer_value = Fraction(answer).limit_denominator()
        distractors = fraction_distractors(answer_value)

        async def verify(string: str) -> bool:
            # 同时接受小数与最简分数形式
            return string.strip() in {str(answer_value), str(answer)}

    return {
        "question": question,
        "answer": verify,
        "options": build_options(str(answer_value), distractors),
    }
