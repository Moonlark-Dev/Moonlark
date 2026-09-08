import random
from typing import Any

from sympy import Symbol, diff, exp, latex, limit, log

from .options import build_options
from .utils import get_verify_function
from ....types import Question
from ....__main__ import lang


def _diff_latex(expr: Any, x: Symbol, order: int = 1) -> str:
    result = expr
    for _ in range(order):
        result = diff(result, x)
    return latex(result).replace(" ", "")


def _ln(x: Symbol) -> Any:
    return log(x)


def _coeff(min_: int, max_: int) -> int:
    return random.choice([i for i in range(min_, max_ + 1) if i != 0])


def _display_sign(index: int, negative: bool, content: str) -> str:
    """生成带正负号的单项显示：首项负号输出 `-...`，其余项输出 `+ ...` / `- ...`。"""
    if index == 0:
        return f"- {content}" if negative else content
    return f"- {content}" if negative else f"+ {content}"


def _generate_simple_terms(x: Symbol, count: int, require_nonlinear: bool = False) -> list[tuple[Any, str]]:
    """按函数模型池随机生成 count 个单一模型项（可重复），保证至少一个非常数项。

    :param require_nonlinear: 二阶求导等场景下要求至少出现一个非线性项，
        避免线性/常数项求导后恒为 0 导致题目退化。
    """
    models: list[tuple[Any, str]] = []
    has_nonlinear = False
    while len(models) < count:
        model = random.choice(
            [
                "const",
                "linear",
                "quadratic",
                "power",
                "exp",
                "a_pow",
                "ln",
                "log_base",
            ],
        )
        match model:
            case "const":
                # 常数项：符号表达式为 1（由系数决定具体数值），显示也由系数决定
                expr, display = 1, None
            case "linear":
                expr, display = x, "x"
            case "quadratic":
                expr, display = x**2, "x^{2}"
                has_nonlinear = True
            case "power":
                n = random.randint(3, 8)
                expr, display = x**n, f"x^{{{n}}}"
                has_nonlinear = True
            case "exp":
                expr, display = exp(x), latex(exp(x))
                has_nonlinear = True
            case "a_pow":
                base = random.randint(2, 9)
                expr, display = base**x, f"{base}^{{x}}"
                has_nonlinear = True
            case "ln":
                expr, display = _ln(x), r"\ln{\left(x \right)}"
                has_nonlinear = True
            case "log_base":
                base = random.randint(2, 9)
                expr, display = log(x, base), rf"\log_{{{base}}}{{\left(x \right)}}"
                has_nonlinear = True
        models.append((expr, display))
    if require_nonlinear and not has_nonlinear:
        # 将最后一项替换为非线性项，保证二阶导数非零
        n = random.randint(3, 8)
        models[-1] = (x**n, f"x^{{{n}}}")
    elif not has_nonlinear:  # 理论极端：全部抽到常数项，替换最后一项为非常数项
        models[-1] = (x, "x")
    return models


def _generate_compound_term(x: Symbol) -> tuple[Any, str]:
    """生成一个由两个函数乘除组成的组合项（整个题目最多出现一个）。"""
    n = random.randint(2, 6)
    base = random.randint(2, 9)
    kind = random.randint(1, 6)
    match kind:
        case 1:
            expr = x**n * _ln(x)
            display = rf"x^{{{n}}} \ln{{\left(x \right)}}"
        case 2:
            expr = x**n * log(x, base)
            display = rf"x^{{{n}}} \log_{{{base}}}{{\left(x \right)}}"
        case 3:
            m = random.randint(1, 3)
            expr = base**x * x**m
            display = rf"{base}^{{x}} x^{{{m}}}"
        case 4:
            m = random.randint(1, 3)
            expr = x**m * exp(x)
            display = rf"x^{{{m}}} e^{{x}}"
        case 5:
            expr = _ln(x) / x**n
            display = rf"\frac{{\ln{{\left(x \right)}}}}{{x^{{{n}}}}}"
        case 6:
            expr = log(x, base) / x**n
            display = rf"\frac{{\log_{{{base}}}{{\left(x \right)}}}}{{x^{{{n}}}}}"
    return expr, display


def _generate_terms(x: Symbol, count: int, require_nonlinear: bool = False) -> tuple[list[tuple[Any, str]], list[int]]:
    """生成 count 个求和项（含至多一个乘除组合项），返回 (项列表, 系数列表)。"""
    terms = _generate_simple_terms(x, count, require_nonlinear)
    if random.random() < 0.5:  # 约一半题目包含一个乘除组合项
        index = random.randrange(count)
        terms[index] = _generate_compound_term(x)
    coefficients = [_coeff(1, 9) for _ in range(count)]
    return terms, coefficients


def _build_function(terms: list[tuple[Any, str]], coefficients: list[int]) -> tuple[Any, str]:
    """将带系数的项列表组装为符号表达式与显示用 LaTeX。"""
    expr = sum(c * term for c, (term, _) in zip(coefficients, terms))
    display_parts = []
    for index, (coefficient, (_, term_display)) in enumerate(zip(coefficients, terms)):
        negative = coefficient < 0
        absolute = abs(coefficient)
        if term_display is None:  # 常数项
            content = str(absolute)
        elif absolute == 1:
            content = term_display
        elif term_display[0].isdigit():
            # 系数与以数字开头的函数（如 a^{x}）之间必须显式用乘号，避免连写歧义
            content = f"{absolute} \\cdot {term_display}"
        else:
            content = f"{absolute}{term_display}"
        display_parts.append(_display_sign(index, negative, content))
    return expr, " ".join(display_parts)


async def generate_limit_question(user_id: str) -> tuple[str, str, list[str]]:
    x = Symbol("x")
    f = random.choice([x**2 + 3 * x - 2, x**3 - 2 * x + 1, x**4 - 4 * x**3 + 5 * x**2 + 2 * x - 1])
    a = random.randint(-10, 10)
    _limit = limit(f, x, a)
    question = await lang.text("question.l7-limit", user_id, a, latex(f))
    answer = latex(_limit)
    variants = [latex(limit(f + k, x, a)) for k in range(1, 7)]
    return question, answer, variants


async def generate_derivative_question(user_id: str, order: int = 1) -> tuple[str, str, list[str]]:
    x = Symbol("x")
    count = random.randint(3, 5)
    terms, coefficients = _generate_terms(x, count, require_nonlinear=order > 1)
    f, display = _build_function(terms, coefficients)
    answer = _diff_latex(f, x, order)
    key = "question.l7-diff-diff" if order == 2 else "question.l7-diff"
    question = await lang.text(key, user_id, display)
    variants: list[str] = []
    for k in range(1, 7):
        # 所有系数同向扰动，避免相邻同类项在 ±k 交替扰动下相互抵消导致干扰项退化
        perturbed = [c + k for c in coefficients]
        f_k, _ = _build_function(terms, perturbed)
        variants.append(_diff_latex(f_k, x, order))
    return question, answer, variants


async def generate_question(user_id: str) -> Question:
    case = random.randint(1, 5)
    if case in (1, 2, 3):
        question, answer, variants = await generate_derivative_question(user_id)
    elif case == 4:
        question, answer, variants = await generate_derivative_question(user_id, 2)
    else:
        question, answer, variants = await generate_limit_question(user_id)
    return {
        "question": question,
        "answer": get_verify_function(answer, user_id),
        "options": build_options(answer, variants),
    }
