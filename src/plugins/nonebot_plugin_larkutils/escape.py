import re

# QQ 官方机器人 markdown 消息中的特殊字符，用于转义展示文本
_MARKDOWN_ESCAPE_RE = re.compile(r"([\\`*_\[\]{}()#+\-!.<>|])")


def escape_markdown(text: str) -> str:
    """转义文本中的 Markdown 特殊字符，避免文本破坏 QQ markdown 消息渲染。"""
    return _MARKDOWN_ESCAPE_RE.sub(r"\\\1", text)
