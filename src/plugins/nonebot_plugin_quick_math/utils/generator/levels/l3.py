import random
from fractions import Fraction
from ....types import Question
from ....__main__ import lang
from .options import build_choices, fraction_distractors, int_distractors


async def generate_question(user_id: str) -> Question:
    a = random.randint(-50, 50)
    b = random.randint(-50, 50)
    question_type = 1 if b == 0 else random.randint(1, 2)  # nosec
    if b < 0:
        question_type += 2
    match question_type:
        case 1 | 3:
            question = await lang.text(f"question.l3-{question_type}", user_id, a, b)
            answer = a * b
            int_answer = True
        case _:
            # 除法题：随机把分子分母同时乘一个 2~5 的数，
            # 保证展示出的分数总是可被化简的
            multiplier = random.randint(2, 5)  # nosec
            question = await lang.text(f"question.l3-{question_type}", user_id, a * multiplier, b * multiplier)
            answer = a / b
            int_answer = False
    if int_answer:
        answer_value: int = int(answer)
        distractors = int_distractors(answer_value)
    else:
        # 分数答案统一以最简分数形式作为选项展示
        answer_value = Fraction(answer).limit_denominator()
        distractors = fraction_distractors(answer_value)

    options, answer_letter = build_choices(str(answer_value), distractors)
    return {
        "question": question,
        "answer": answer_letter,
        "options": options,
    }
