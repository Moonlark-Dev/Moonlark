import math
from nonebot_plugin_openai.types import Message as OpenAIMessage
from .types import CachedMessage


def calculate_trigger_probability(accumulated_length: int) -> float:
    """
    根据累计文本长度计算触发概率

    测试：
    0 字 ->  0.00%
    10 字 ->  2.53%
    20 字 ->  3.72%
    30 字 ->  5.45%
    40 字 ->  7.90%
    50 字 -> 11.32%
    60 字 -> 15.96%
    70 字 -> 21.99%
    80 字 -> 29.45%
    90 字 -> 38.12%
    100 字 -> 47.50%
    110 字 -> 56.88%
    120 字 -> 65.55%
    130 字 -> 73.01%
    140 字 -> 79.04%
    150 字 -> 83.68%
    160 字 -> 87.10%
    180 字 -> 91.28%
    200 字 -> 93.29%

    使用 sigmoid 函数变体实现平滑过渡
    """
    if accumulated_length <= 0:
        return 0.0

    # 使用修改的 sigmoid 函数: P(x) = 0.95 / (1 + e^(-(x-100)/25))
    # 中心点在100字，斜率适中

    probability = 0.95 / (1 + math.exp(-(accumulated_length - 100) / 25))

    return max(0.0, min(0.95, probability))


def generate_message_string(message: CachedMessage) -> str:
    return f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]({message['message_id']}): {message['content']}\n"


def get_role(message: OpenAIMessage) -> str:
    if isinstance(message, dict):
        role = message["role"]
    else:
        role = message.role
    return role
