"""L8：矩阵乘法。

题目给出两个矩阵 A（m×n）与 B（n×p），要求计算 A·B。与低等级题目不同，
题面和选项都是矩阵，因此该等级在 QQ 官方机器人下也会把题目信息渲染成图片
（见 ``utils/question.py`` 的 ``_QUESTION_IMAGE_LEVELS``），否则 LaTeX 的
``pmatrix`` 会以原始文本发送，无法辨认。

干扰项按“预测常见错误”设计，而不是随机数字：

- 转置项：结果正确但行列互换；
- 哈达玛积项：把对应元素直接相乘（只在两个因子同型时有意义）；
- 行乘行项：把 B 按行取，即计算 A·Bᵀ；
- 漏加项：每个点积只累加前 n-1 个乘积；
- 错位项：把 b_{k,j} 错写成 b_{k,j+1}（列下标错位）；
- 顺序颠倒项：计算 B·A（维度允许时），对应“乘法不满足交换律”的经典错误；
- 维度错误项：混入一个形状与 A·B 不符的矩阵；
- 数值扰动项：在正确答案上改动一个元素，作为兜底干扰项。
"""

import random

from ....types import Question
from ....__main__ import lang
from .options import build_choices

Matrix = list[list[int]]

# (A 的行, A 的列 / B 的行, B 的列)：2×2 最常见，另外两种用于考查维度对齐
_SHAPES: list[tuple[int, int, int]] = [
    (2, 2, 2),
    (2, 2, 2),
    (2, 3, 2),
    (2, 3, 3),
    (3, 2, 3),
]


def _random_matrix(rows: int, cols: int, bound: int) -> Matrix:
    """生成一个元素在 [-bound, bound] 内且不全为零的矩阵。"""
    while True:
        matrix = [[random.randint(-bound, bound) for _ in range(cols)] for _ in range(rows)]
        if any(value for row in matrix for value in row):
            return matrix


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    """按定义计算 left·right，并返回结果矩阵。"""
    inner = len(right)
    cols = len(right[0])
    return [[sum(left[i][k] * right[k][j] for k in range(inner)) for j in range(cols)] for i in range(len(left))]


def _transpose(matrix: Matrix) -> Matrix:
    return [list(row) for row in zip(*matrix)]


def _hadamard(left: Matrix, right: Matrix) -> Matrix | None:
    """对应元素相乘（哈达玛积）；两个矩阵不同型时没有定义。"""
    if len(left) != len(right) or any(len(a) != len(b) for a, b in zip(left, right)):
        return None
    return [[a * b for a, b in zip(row_a, row_b)] for row_a, row_b in zip(left, right)]


def _row_dot_row(left: Matrix, right: Matrix) -> Matrix | None:
    """把 B 按行取：计算 A·Bᵀ（仅当 B 为方阵时有定义）。"""
    if len(right) != len(right[0]):
        return None
    return _multiply(left, _transpose(right))


def _missing_last_term(left: Matrix, right: Matrix) -> Matrix:
    """漏加项：每个元素只累加前 n-1 个乘积。"""
    inner = len(right) - 1
    return [
        [sum(left[i][k] * right[k][j] for k in range(inner)) for j in range(len(right[0]))] for i in range(len(left))
    ]


def _shifted_columns(left: Matrix, right: Matrix) -> Matrix:
    """错位项：把 b_{k,j} 错写成 b_{k,j+1}（最后一列循环回第一列）。"""
    cols = len(right[0])
    return [
        [sum(left[i][k] * right[k][(j + 1) % cols] for k in range(len(right))) for j in range(cols)]
        for i in range(len(left))
    ]


def _reversed_order(left: Matrix, right: Matrix) -> Matrix | None:
    """顺序颠倒项：计算 B·A（仅当 B 的列数等于 A 的行数时有定义）。"""
    if len(right[0]) != len(left):
        return None
    return _multiply(right, left)


def _wrong_shape(answer: Matrix) -> Matrix:
    """维度错误项：构造一个形状与正确答案不符的矩阵。"""
    rows, cols = len(answer), len(answer[0])
    if (rows, cols) == (2, 2):
        return _random_matrix(3, 2, 3)
    if rows == cols:
        return _random_matrix(rows - 1, cols, 3)
    return _random_matrix(cols, rows, 3)


def _perturbed(answer: Matrix) -> Matrix:
    """把答案中随机一个元素加上 ±1/±2，作为兜底干扰项。"""
    result = [row[:] for row in answer]
    row = random.randrange(len(result))
    col = random.randrange(len(result[0]))
    result[row][col] += random.choice([-2, -1, 1, 2])
    return result


def matrix_latex(matrix: Matrix) -> str:
    """把矩阵转为 LaTeX ``pmatrix``（不加 ``$``，由渲染层统一包裹）。"""
    body = " \\\\ ".join(" & ".join(str(value) for value in row) for row in matrix)
    return f"\\begin{{pmatrix}} {body} \\end{{pmatrix}}"


def build_distractors(left: Matrix, right: Matrix, answer: Matrix) -> list[Matrix]:
    """按常见错误生成干扰项池（调用方负责去重与截断）。"""
    candidates = [
        _transpose(answer),
        _hadamard(left, right),
        _row_dot_row(left, right),
        _missing_last_term(left, right),
        _shifted_columns(left, right),
        _reversed_order(left, right),
        _wrong_shape(answer),
    ]
    matrices = [matrix for matrix in candidates if matrix is not None]
    matrices.extend(_perturbed(answer) for _ in range(2))
    return matrices


async def generate_question(user_id: str) -> Question:
    rows, inner, cols = random.choice(_SHAPES)
    # 结果元素越多、点积越长，数字就越小，避免选项里的数值过大
    bound = 6 if rows * cols * inner <= 8 else 4
    left = _random_matrix(rows, inner, bound)
    right = _random_matrix(inner, cols, bound)
    answer = _multiply(left, right)

    question = await lang.text("question.l8", user_id, matrix_latex(left), matrix_latex(right))
    options, answer_letter = build_choices(
        matrix_latex(answer),
        (matrix_latex(matrix) for matrix in build_distractors(left, right, answer)),
    )
    return {
        "question": question,
        "answer": answer_letter,
        "options": options,
    }
