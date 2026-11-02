"""消息 Token 的计费口径。

只对「有效字」计费：语气词和标点是说话的语气，不该被当成篇幅罚款。按旧口径
（每 7 个字 1 Token、语气词也算字数）模型会为了省额度把话压成电报，这正是
「AI 味」的来源之一。
"""

import math

# 不计费字符：中英文标点、空白，以及语气词/感叹词（单字）
EXEMPT_CHARS = frozenset(
    "，。！？、；：…～—·,.!?;:'\"“”‘’（）()【】《》<> \n\t\r~" "啊呀呢嘛啦哦吧咯呐捏哟呦喵唔诶欸嘿哈呵嘻唉哎嗯喔嗷呜哇",
)
# 单条消息最多豁免的字符数：防止「喵喵喵……」把额度白嫖干净
MAX_EXEMPT_CHARS = 12
# 每多少有效字消耗 1 Token（旧口径为 7 个字）
CHARS_PER_TOKEN = 8


def exempt_char_count(text: str) -> int:
    """统计本条消息可豁免的字符数（封顶 ``MAX_EXEMPT_CHARS``）。"""
    return min(sum(1 for char in text if char in EXEMPT_CHARS), MAX_EXEMPT_CHARS)


def effective_length(text: str) -> int:
    """有效字数：总字数减去可豁免的语气词与标点。"""
    return max(0, len(text) - exempt_char_count(text))


def calculate_token_cost(text: str) -> int:
    """计算一条消息应扣的 Token。

    每条消息至少 1 Token：单字消息、纯语气词消息也照样收费，避免把一句完整的话
    切成碎片发送反而不花钱。
    """
    if not text:
        return 0
    return max(1, math.ceil(effective_length(text) / CHARS_PER_TOKEN))
