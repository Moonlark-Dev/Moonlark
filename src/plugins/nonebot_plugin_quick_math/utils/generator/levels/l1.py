import random
from ....types import Question
from ....__main__ import lang


async def generate_question(user_id: str) -> Question:
    a = random.randint(-10, 10)
    b = random.randint(-10, 10)
    question_type = random.randint(1, 3)
    if question_type != 3 and b < 0:
        b *= -1
    elif question_type == 3 and b < 0:
        question_type = 4
    match question_type:
        case 1:
            question = await lang.text("question.l1-1", user_id, a, b)
            answer = str(a + b)
        case 2:
            question = await lang.text("question.l1-2", user_id, a, b)
            answer = str(a - b)
        case 3:
            question = await lang.text("question.l1-3", user_id, a, b)
            answer = str(a * b)
        case _:
            question = await lang.text("question.l1-4", user_id, a, b)
            answer = str(a * b)
    return {"question": question, "answer": answer}
