import hashlib
from nonebot.adapters import Message as BaseMessage


def compute_message_hash(message: BaseMessage) -> bytes:
    """计算消息的 SHA-256 哈希值（用于可靠的消息匹配）

    OneBot V11 / V12 / QQ 三种适配器的 Message 均支持 str()，
    此处保留通用 fallback 以备未来适配器不兼容之需。
    """
    try:
        raw = str(message)
    except Exception:
        raw = "".join(str(seg) for seg in message)

    return hashlib.sha256(raw.encode("utf-8")).digest()
