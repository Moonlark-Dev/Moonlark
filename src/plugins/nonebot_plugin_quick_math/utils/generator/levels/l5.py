import copy
import json
import random
from typing import Any, Generator, Optional
import sympy as sp
import re

from .....nonebot_plugin_openai.utils.message import generate_message

from ....exceptions import GenerateFailed

from ....config import config
from .....nonebot_plugin_openai.utils.chat import fetch_messages
from ....types import Question
from ....__main__ import lang

AI_PROMPT = """
# OBJECTIVE # Next, I will give you a solution to a mathematical equation and ask you to generate four wrong interference terms in a format similar to the four answers to a multiple choice question. Methods for generating interferences include, but are not limited to, number substitutions, modifying positive and negative numbers, and so on. There must be at least 2 interference terms in which at least 1 arbitrary number is replaced and 1 positive or negative number is modified. # RESPONSE # Directly output a json list (do not wrap in quotes, output in one line) containing the four interfering answers. # EXAMPLE # {}
"""
QUADRATIC_EXAMPLE = r"""["$x_1 = xxx, \quad x_2 = xxx$", "$x_1 = xxx, \quad x_2 = xxx$", "$x_1 = xxx, \quad x_2 = xxx$", "$x_1 = xxx, \quad x_2 = xxx$"]"""
LINEAR_EQUATION = r"""["$x = xxx$", "$x = xxx$", "$x = xxx$", "$x = xxx$"]"""
CHOICE_LETTER = ["A", "B", "C", "D", "E"]


def quadratic_solver(a: int, b: int, c: int):
    x = sp.symbols("x")
    equation = a * x**2 + b * x + c
    solutions = sp.solve(equation, x)

    def format_solution(sol):
        if sol.is_rational:
            return sp.latex(sp.nsimplify(sol))
        elif sol.is_real and not sol.is_rational:
            return sp.latex(sp.simplify(sol))
        else:
            return sp.latex(sp.simplify(sol))

    formatted_solutions = [format_solution(sol) for sol in solutions]
    if len(formatted_solutions) == 1:
        return f"$x = {formatted_solutions[0]}$$"
    elif len(formatted_solutions) == 2:
        return f"$x_1 = {formatted_solutions[0]}, \\quad x_2 = {formatted_solutions[1]}$"
    elif len(formatted_solutions) == 0:
        return "No solutions"
    else:
        return ", ".join([f"$x_{i+1} = {sol}$" for i, sol in enumerate(formatted_solutions)])


def parse_int(a: int) -> str:
    num = {
        -1: "-",
        1: "",
    }.get(a, str(a))
    return f"+{num}" if a > 0 else f"{num}"


async def get_raw_choices(right_answer: str, user_id) -> re.Match[str] | None:
    messages = [
        generate_message(AI_PROMPT.format(QUADRATIC_EXAMPLE if "x_1" in right_answer else LINEAR_EQUATION), "system"),
        generate_message(right_answer, "user"),
    ]
    content = re.search(
        r"\[.+\]",
        await fetch_messages(
            messages,
            user_id,
            temperature=0.8,
            top_p=0.95,
        ),
    )
    return content


def parse_choice(answer: str) -> list[str]:
    return answer.replace("$", "").replace("_1", "").replace("_2", "").split(", \\quad")


def check_same_choice(right_answer: str, choices: list[str]) -> Generator[int, Any, None]:
    parsed_right_answer = parse_choice(right_answer)
    for i, choice in enumerate(choices):
        parsed_choice = parse_choice(choice)
        if parsed_choice[0] in parsed_right_answer and parsed_choice[1] in parsed_right_answer:
            yield i


async def generate_question(user_id: str) -> Question:
    a = random.randint(-10, 10)
    b = random.randint(-20, 20)
    c = random.randint(-30, 30)
    question = ""
    if a != 0:
        question += await lang.text("question.l5-a", user_id, a)
    if b != 0:
        question += await lang.text("question.l5-b", user_id, parse_int(b))
    if b != 0:
        question += await lang.text("question.l5-c", user_id, parse_int(c))
    for t in "+-":
        question = question.replace(t, await lang.text("question.l5-o", user_id, t))
    right_answer = quadratic_solver(a, b, c)
    if right_answer == "No solutions":
        right_answer = await lang.text("question.l5-n", user_id)
    choices = [right_answer]
    for _ in range(config.qm_gpt_max_retry):
        content = await get_raw_choices(right_answer, user_id)
        if content:
            break
    else:
        raise GenerateFailed()
    choices.extend(json.loads(content[0].replace("\\", "\\\\")))
    for _index in check_same_choice(right_answer, copy.deepcopy(choices[1:])):
        index = _index + 1
        choices[index] = await lang.text("question.l5-s", user_id)
    random.shuffle(choices)
    answer = CHOICE_LETTER[choices.index(right_answer)]
    question = await lang.text("question.l5", user_id, question, *choices)
    return {"question": question, "answer": answer}
