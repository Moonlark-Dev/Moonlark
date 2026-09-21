"""检测纯文本中伪装成富文本占位符的内容。

Moonlark 在解析消息时，会把图片、视频、文件、回复等消息段渲染成
``[关键字(...)]`` 形式的占位符（见 ``lang/zh_hans/chat.yaml`` 的 ``parser`` 段）。
用户完全可以在纯文本里手写出一模一样的字符串，仅从格式化后的文本无法区分，
因此需要在格式化消息时把这些片段单独挑出来提示模型。
"""

import re

# 富文本占位符的关键字，与 parser.* 文案中使用的关键字保持一致。
RICH_TEXT_KEYWORDS = (
    "图片",
    "视频",
    "文件",
    "回复",
    "合并转发",
    "特殊消息",
    "戳一戳",
    "表情",
    "emoji",
)

# [关键字] / [关键字: 说明] / [关键字(参数)] / [关键字(参数): 说明]
# 说明部分不允许跨行，避免把一大段文本整体吞掉。
RICH_TEXT_PLACEHOLDER_PATTERN = re.compile(
    r"\[(?:{keywords})(?:[（(][^）)\]\r\n]*[）)])?[^\]\r\n]*\]".format(
        keywords="|".join(re.escape(keyword) for keyword in RICH_TEXT_KEYWORDS),
    ),
)


def find_fake_rich_text(text: str) -> list[str]:
    """找出纯文本中与富文本占位符格式相同的片段。

    返回的片段保持出现顺序并按原文去重；调用方应只在真正的文本消息段上调用本函数，
    Moonlark 自行渲染出的占位符不属于“伪造内容”。
    """
    if not text:
        return []
    found: list[str] = []
    for match in RICH_TEXT_PLACEHOLDER_PATTERN.finditer(text):
        placeholder = match.group(0)
        if placeholder not in found:
            found.append(placeholder)
    return found
