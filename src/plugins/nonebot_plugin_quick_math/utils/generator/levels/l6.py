import copy
import json
import random
from typing import Generator, Optional
import sympy as sp
import re

from .l5 import parse_int

from nonebot_plugin_openai.utils.message import generate_message

from ....exceptions import GenerateFailed

from ....config import config
from nonebot_plugin_openai.utils.chat import fetch_messages
from ....types import Question
from ....__main__ import lang

AI_PROMPT = """# OBJECTIVE # You will be given the result of a polynomial after simplification. I need a multiple choice question based on this result as an answer, please generate two wrong answers that are completely different from the correct result, it should look like a randomized expression but contain no trigonometric functions and no letters. The wrong answers should be disorienting; their goal is to confuse the respondent and make it difficult for them to pick the correct answer.
# RESPONSE # Directly output a json list containing the two wrong answers you generated. No need to output the curly braces, and don't wrap them in any quotes.
# YOUR OUTPUT EXAMPLE #
["{wrong_answer_1}","{wrong_answer_2}"]"""


async def get_wrong_answer(
    right_answer: str, question: str, user_id: str, retry: int = config.qm_gpt_max_retry
) -> list[str]:
    messages = [
        generate_message(AI_PROMPT, "system"),
        generate_message(f"{right_answer}", "user"),
    ]
    content = re.search(
        r"\[.+\]",
        await fetch_messages(
            messages,
            user_id,
            temperature=0.8,
            top_p=0.9,
        ),
    )
    if content is None and retry > 0:
        return await get_wrong_answer(right_answer, question, user_id, retry - 1)
    elif content is not None:
        return json.loads(content[0].replace("\\", "\\\\"))
    else:
        raise GenerateFailed()


def evaluate_trig_functions(angle_degrees: int):
    angle_radians = sp.rad(angle_degrees)
    sin_value = sp.sin(angle_radians)
    cos_value = sp.cos(angle_radians)
    tan_value = sp.tan(angle_radians)
    return sin_value, cos_value, tan_value


async def generate_question(user_id: str) -> Question:
    _num = random.randint(5, 100) ** 2
    c = random.randint(3, 5)
    question = f"{c}\\sqrt {{{_num}}}"
    answer = sp.sqrt(_num) * sp.Integer(c)
    for _ in range(random.randint(3, 5)):
        match random.randint(1, 8):
            case 1:
                a = random.choice([i for i in range(-5, 6) if i != 0])
                b = 15 * random.randint(1, 10)
                question += f"{parse_int(a)}\\sin {b}^\\circ"
                answer += evaluate_trig_functions(b)[0] * a
            case 2:
                a = random.choice([i for i in range(-5, 6) if i != 0])
                b = 15 * random.randint(1, 10)
                question += f"{parse_int(a)}\\cos {b}^\\circ"
                answer += evaluate_trig_functions(b)[1] * a
            case 3:
                a = random.choice([i for i in range(-5, 6) if i != 0])
                b = 15 * random.choice([i for i in range(1, 13) if i != 90])
                question += f"{parse_int(a)}\\tan {b}^\\circ"
                answer += evaluate_trig_functions(b)[2] * a
            case _:
                a = random.choice([i for i in range(-75, 76) if i != 0])
                question += parse_int(a)
                answer += sp.Integer(a)
    choices = [sp.latex(answer.expand().simplify())]
    right_answer = choices[0]
    choices.extend(await get_wrong_answer(choices[0], question, user_id))
    random.shuffle(choices)
    right_choice = ["A", "B", "C"][choices.index(right_answer)]
    return {
        "answer": right_choice,
        "question": await lang.text("question.l6", user_id, question, *choices),
    }
