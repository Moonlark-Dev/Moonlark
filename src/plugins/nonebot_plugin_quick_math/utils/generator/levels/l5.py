import random
import sympy as sp

from .utils import parse_int, get_verify_function
from ....types import Question
from ....__main__ import lang


def format_solution(sol):
    if sol.is_rational:
        return sp.latex(sp.nsimplify(sol))
    elif sol.is_real and not sol.is_rational:
        return sp.latex(sp.simplify(sol))
    else:
        return sp.latex(sp.simplify(sol))


def quadratic_solver(a: int, b: int, c: int) -> str:
    x = sp.symbols("x")
    equation = a * x**2 + b * x + c
    solutions = sp.solve(equation, x)
    formatted_solutions = [format_solution(sol) for sol in solutions]
    if len(formatted_solutions) == 1:
        return f"x = {formatted_solutions[0]}"
    elif len(formatted_solutions) == 0:
        return "No solutions"
    else:
        return ", ".join([f"x_{i+1} = {sol}" for i, sol in enumerate(formatted_solutions)])


async def generate_question(user_id: str) -> Question:
    a = random.randint(-10, 10)
    b = random.randint(-20, 20)
    c = random.randint(-30, 30)
    question = ""
    if a != 0:
        question += await lang.text("question.l5-a", user_id, a)
    if b != 0:
        question += await lang.text("question.l5-b", user_id, parse_int(b))
    question += await lang.text("question.l5-c", user_id, parse_int(c))
    for t in "+-":
        question = question.replace(t, await lang.text("question.l5-o", user_id, t))
    right_answer = quadratic_solver(a, b, c)
    question = await lang.text("question.l5", user_id, question)
    return {"question": question, "answer": get_verify_function(right_answer, user_id)}
