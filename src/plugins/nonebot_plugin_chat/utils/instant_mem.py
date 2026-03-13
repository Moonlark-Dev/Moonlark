

from datetime import datetime, timedelta
from typing import Generator, Literal, TypedDict


class InstantMemory(TypedDict):
    category: Literal[
        "myself",
        "emotion",
        "opinion",
        "goal",
        "activity"
    ]
    content: str
    keywords: list[str]
    create_time: datetime
    recall_level: int

BASE_EXPIRE_TIME = {
    "myself": None,
    "emotion": timedelta(minutes=12),
    "opinion": timedelta(minutes=30),
    "goal": timedelta(days=1),
    "activity": timedelta(minutes=10),
}

instant_memories: list[InstantMemory] = []

def post_instant_memory(
    category: Literal[
        "myself",
        "emotion",
        "opinion",
        "goal",
        "activity"
    ],
    content: str,
    keywords: list[str],
) -> None:
    """
    post instant memory
    """
    instant_memories.append({
        "category": category,
        "content": content,
        "keywords": keywords,
        "create_time": datetime.now(),
        "recall_level": 0,
    })

def filter_instant_memory(chat_history: str) -> Generator[InstantMemory, None, None]:
    for memory in instant_memories:
        if any(keyword in chat_history for keyword in memory["keywords"]):
            memory["recall_level"] += 1
            yield memory
    clear_expired_instant_memory()

def clear_expired_instant_memory() -> None:
    global instant_memories
    instant_memories = [
        memory for memory in instant_memories
        if BASE_EXPIRE_TIME[memory["category"]] is None or datetime.now() - memory["create_time"] < min(timedelta(hours=30), BASE_EXPIRE_TIME[memory["category"]] * (1 + 0.1 * memory["recall_level"]))
    ]



