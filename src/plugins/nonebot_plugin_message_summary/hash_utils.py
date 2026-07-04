import hashlib
from nonebot.adapters import Message as BaseMessage


def compute_message_hash(message: BaseMessage) -> bytes:
    """计算消息的 SHA-256 哈希值（用于可靠的消息匹配）"""
    try:
        raw = str(message)
    except Exception:
        # 如果 str() 失败，按适配器类型处理
        from nonebot.adapters.onebot.v11 import Message as OB11Message
        from nonebot.adapters.onebot.v12 import Message as OB12Message
        from nonebot.adapters.qq.message import Message as QQMessage

        if isinstance(message, OB11Message):
            raw = "".join(str(seg) for seg in message)
        elif isinstance(message, OB12Message):
            raw = "".join(str(seg) for seg in message)
        elif isinstance(message, QQMessage):
            raw = "".join(str(seg) for seg in message)
        else:
            raw = repr(message)

    return hashlib.sha256(raw.encode("utf-8")).digest()
