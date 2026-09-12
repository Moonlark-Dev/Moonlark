"""LaTeX 公式的文本处理工具。

题目生成器产生的是裸 LaTeX（例如选项 ``x_{1} = \\frac{1}{2}``）。题目信息在
QQ 官方机器人下通过 md_to_pic 渲染成图片，因此需要 :func:`ensure_math_mode` 把
裸 LaTeX 包进 ``$...$`` 交给 KaTeX；图床不可用需要回退为纯文本时，则用
:func:`latex_to_plain` 把公式转换为可读的 Unicode 符号。转换失败时保持原样，
由调用方兜底。
"""

import re

_SUPERSCRIPT_PATTERN = re.compile(r"\^\{([^{}]*)\}|\^([0-9+\-()a-zA-Z])")
_SUBSCRIPT_PATTERN = re.compile(r"_\{([^{}]*)\}|_([0-9+\-()a-zA-Z])")

# 裸 LaTeX 的特征：命令反斜杠、上下标、花括号
_LATEX_HINT_PATTERN = re.compile(r"[\\_^{}]")

_SUPERSCRIPT_MAP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
_SUBSCRIPT_MAP = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")

# 常见 LaTeX 命令 → 纯文本
_COMMANDS = {
    "times": "×",
    "div": "÷",
    "cdot": "·",
    "pm": "±",
    "mp": "∓",
    "circ": "°",
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "log": "log",
    "ln": "ln",
    "pi": "π",
    "infty": "∞",
}


def _translate_script(match: re.Match, script_map: str) -> str:
    content = match.group(1) or match.group(2)
    return content.translate(script_map)


def ensure_math_mode(latex: str) -> str:
    """把裸 LaTeX 包进 ``$...$``，供 md_to_pic 交给 KaTeX 渲染。

    题目生成器给出的选项是裸 LaTeX（如 ``x_{1} = \\frac{1}{2}``），而 md_to_pic
    只把 ``$...$``/``$$...$$`` 包裹的内容当作公式；纯数字选项（如 ``1/2``）没有
    公式特征，保持原样以免平白变成数学字体。
    """
    if not latex or latex.lstrip().startswith("$") or _LATEX_HINT_PATTERN.search(latex) is None:
        return latex
    return f"${latex}$"


def latex_to_plain(latex: str) -> str:
    """将 LaTeX 字符串转换为可读的纯文本（尽力而为，不保证数学等价）。"""
    if not latex:
        return latex
    # 去除文档级公式包裹符（$$..$$ / $..$ / \(..\)）
    text = re.sub(r"\$\$", "", latex)
    text = re.sub(r"\$", "", text)
    text = re.sub(r"\\[()]", "", text)
    # 分式 a/b 与根式 √
    text = re.sub(r"\\dfrac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", lambda m: f"({m.group(1)})/({m.group(2)})", text)
    text = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", lambda m: f"({m.group(1)})/({m.group(2)})", text)
    text = re.sub(r"\\sqrt\s*\{([^{}]*)\}", lambda m: f"√({m.group(1)})", text)
    # 常见命令
    for command, replacement in _COMMANDS.items():
        text = re.sub(rf"\\{command}\b", replacement, text)
    # 上下标
    text = _SUPERSCRIPT_PATTERN.sub(lambda m: _translate_script(m, _SUPERSCRIPT_MAP), text)
    text = _SUBSCRIPT_PATTERN.sub(lambda m: _translate_script(m, _SUBSCRIPT_MAP), text)
    # 清理剩余的命令、花括号与残留符号
    text = re.sub(r"\\left|\\right|\\,", "", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", "", text)
    text = text.replace("{", "").replace("}", "").replace("^", "").replace("_", "")
    return re.sub(r"\s+", " ", text).strip()
