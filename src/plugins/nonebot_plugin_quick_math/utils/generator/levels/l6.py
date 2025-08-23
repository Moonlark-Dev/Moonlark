import copy
import json
import random
from typing import Generator, Optional
import sympy as sp
import re

from .utils import parse_int, get_verify_function

from nonebot_plugin_openai.utils.message import generate_message

from ....exceptions import GenerateFailed

from ....config import config
from nonebot_plugin_openai.utils.chat import fetch_message
from ....types import Question
from ....__main__ import lang


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
    return {
        "answer": get_verify_function(answer, user_id),
        "question": await lang.text("question.l6", user_id, question),
    }
