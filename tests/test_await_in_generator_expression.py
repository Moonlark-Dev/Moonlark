"""回归：函数里不能用「含 await 的生成器表达式」。

``(await f(x) for x in items)`` 会被编译成异步生成器（async generator），
它不是可迭代对象：``"".join(...)``、``list(...)`` 等同步消费都会直接抛
``TypeError``。列表/集合/字典推导式会被内联进外层协程，不受此限制，只有
生成器表达式有这个问题——而它往往只在运行到那一行时才炸，看起来就像指令
「无响应」（例如 nonebot_plugin_craft 的 ``/craft`` 主菜单）。
"""

import ast
import pathlib

SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"


def iter_python_files() -> list[pathlib.Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def find_await_in_generator_expression(tree: ast.AST) -> list[tuple[int, str]]:
    return [
        (node.lineno, ast.unparse(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.GeneratorExp) and any(isinstance(child, ast.Await) for child in ast.walk(node))
    ]


def test_no_await_in_generator_expression() -> None:
    offenders: list[str] = []
    for path in iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, source in find_await_in_generator_expression(tree):
            offenders.append(f"{path.relative_to(SOURCE_ROOT.parent)}:{lineno}: {source}")
    assert (
        not offenders
    ), "生成器表达式里不能出现 await（异步生成器不可迭代），请改成显式循环或列表推导式：\n" + "\n".join(offenders)
