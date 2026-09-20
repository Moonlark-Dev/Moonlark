import re

# QQ 官方机器人 markdown 消息中的特殊字符，用于转义展示文本
_MARKDOWN_ESCAPE_RE = re.compile(r"([\\`*_\[\]{}()#+\-!.<>|])")

# `<qqbot-cmd-input>` 标签属性中会破坏标签解析的保留字符
_CMD_INPUT_ESCAPE_RE = re.compile(r"[<>&\"'%]")


def escape_markdown(text: str) -> str:
    """转义文本中的 Markdown 特殊字符，避免文本破坏 QQ markdown 消息渲染。"""
    return _MARKDOWN_ESCAPE_RE.sub(r"\\\1", text)


def escape_cmd_input(text: str, urlencode: bool = True) -> str:
    """转义 `<qqbot-cmd-input>` 标签的 text/show 属性值。

    QQ 官方要求指令组件的 text/show 属性值需 urlencode 后传递，否则带上尖括号
    占位符（如 `shop buy <编号> [数量]`）的用法会导致平台返回
    "qqbot-cmd-input参数解析失败"。整体百分号编码会使较长中文用法远超官方
    100 字符限制，因此仅编码会破坏标签解析的保留字符，中文及常规字符保持原样，
    平台按 urlencode 解码后即可还原原文。

    Args:
        text: 待转义的文本
        urlencode: 为 False 时只把换行替换为空格，不做百分号编码
    """
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if not urlencode:
        return text
    return _CMD_INPUT_ESCAPE_RE.sub(lambda m: f"%{ord(m.group()):02X}", text)
