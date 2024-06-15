import random
from fractions import Fraction
from ....types import Question
from ....__main__ import lang


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
        case _:
            answer = a / b
    if int(answer) != answer:
        fraction = Fraction(answer).limit_denominator()
        answer = str(answer).replace(".", r"\.")
        answer = f"({answer}|{fraction})"
    return {"question": question, "answer": str(answer)}
