"""LaTeX 到纯文本的轻量转换。

QQ 官方机器人 markdown 消息不解析 LaTeX 数学公式，因此在 QQ 适配器下发送题目卡片时，
将题目生成器产生的 LaTeX 字符串转换为可读的纯文本（Unicode 符号），
以便直接嵌入 markdown 消息。转换失败时保持原样，由调用方兜底。
"""

import re

_SUPERSCRIPT_PATTERN = re.compile(r"\^\{([^{}]*)\}|\^([0-9+\-()a-zA-Z])")
_SUBSCRIPT_PATTERN = re.compile(r"_\{([^{}]*)\}|_([0-9+\-()a-zA-Z])")

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
