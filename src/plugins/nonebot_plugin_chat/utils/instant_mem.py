from datetime import datetime, timedelta
from typing import Generator, Literal, TypedDict


class InstantMemory(TypedDict):
    category: Literal["myself", "emotion", "opinion", "goal", "activity"]
    content: str
    keywords: list[str]
    create_time: datetime
    recall_level: int
    expire_level: int


# 每个 category 独立的过期时间等级映射表
# Level 1-5 对应不同的过期时长
EXPIRE_TIME_MAP = {
    "myself": {
        1: timedelta(minutes=30),
        2: timedelta(hours=2),
        3: timedelta(hours=6),
        4: timedelta(hours=12),
        5: None,  # 永久
    },
    "emotion": {
        1: timedelta(minutes=1),
        2: timedelta(minutes=5),
        3: timedelta(minutes=15),
        4: timedelta(minutes=30),
        5: timedelta(hours=1),
    },
    "opinion": {
        1: timedelta(minutes=5),
        2: timedelta(minutes=15),
        3: timedelta(minutes=30),
        4: timedelta(hours=1),
        5: timedelta(hours=3),
    },
    "goal": {
        1: timedelta(minutes=30),
        2: timedelta(hours=2),
        3: timedelta(hours=6),
        4: timedelta(hours=12),
        5: timedelta(hours=24),
    },
    "activity": {
        1: timedelta(minutes=2),
        2: timedelta(minutes=10),
        3: timedelta(minutes=30),
        4: timedelta(hours=1),
        5: timedelta(hours=3),
    },
}

instant_memories: list[InstantMemory] = []


def post_instant_memory(
    category: Literal["myself", "emotion", "opinion", "goal", "activity"],
    content: str,
    keywords: list[str],
    expire_level: int,
) -> None:
    """
    post instant memory
    """
    # 确保 expire_level 在 1-5 范围内
    expire_level = max(1, min(5, expire_level))
    
    instant_memories.append(
        {
            "category": category,
            "content": content,
            "keywords": keywords,
            "create_time": datetime.now(),
            "recall_level": 0,
            "expire_level": expire_level,
        }
    )


def filter_instant_memory(chat_history: str) -> Generator[InstantMemory, None, None]:
    for memory in instant_memories:
        if any(keyword in chat_history for keyword in memory["keywords"]):
            memory["recall_level"] += 1
            yield memory
    clear_expired_instant_memory()


def clear_expired_instant_memory() -> None:
    global instant_memories
    instant_memories = [
        memory
        for memory in instant_memories
        if _is_memory_valid(memory)
    ]


def _is_memory_valid(memory: InstantMemory) -> bool:
    """检查记忆是否未过期"""
    category = memory["category"]
    expire_level = memory["expire_level"]
    create_time = memory["create_time"]
    recall_level = memory["recall_level"]
    
    # 获取基础过期时间
    base_expire_time = EXPIRE_TIME_MAP[category].get(expire_level, timedelta(minutes=30))
    
    # 永久保存的记忆
    if base_expire_time is None:
        return True
    
    # 根据 recall_level 延长过期时间（每次召回增加 10%）
    adjusted_expire_time = base_expire_time * (1 + 0.1 * recall_level)
    
    # 最长不超过 30 小时
    max_expire_time = timedelta(hours=30)
    adjusted_expire_time = min(adjusted_expire_time, max_expire_time)
    
    return datetime.now() - create_time < adjusted_expire_time
