import hashlib
from nonebot import logger
from nonebot.adapters import Message as BaseMessage


def compute_message_hash(message: BaseMessage) -> bytes:
    """计算消息的 SHA-256 哈希值（用于可靠的消息匹配）

    OneBot V11 / V12 / QQ 三种适配器的 Message 均支持 str()。
    """
    logger.debug(f"{message=}")
    return hashlib.sha256(str(message).encode("utf-8")).digest()
