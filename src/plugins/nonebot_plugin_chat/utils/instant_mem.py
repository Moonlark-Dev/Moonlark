from datetime import datetime, timedelta
from typing import Generator, Literal, TypedDict

from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot.log import logger
import json
import re

from ..lang import lang


class InstantMemory(TypedDict):
    category: Literal["myself", "emotion", "opinion", "goal", "activity"]
    content: str
    keywords: list[str]
    create_time: datetime
    recall_level: int
    expire_level: int
    ctx_id: str
    name: str


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


def get_instant_memories() -> list[InstantMemory]:
    clear_expired_instant_memory()
    return instant_memories


async def detect_conflicts_with_llm(
    new_category: str,
    new_content: str,
    new_keywords: list[str],
    existing_memories: list[InstantMemory],
    lang_str: str = "zh_tw",
) -> list[int]:
    """
    使用 LLM 检测新记忆与已有记忆的冲突

    Args:
        lang_str: 语言代码，用于本地化提示词

    Returns:
        冲突记忆的索引列表
    """
    if not existing_memories:
        return []

    # 构建已有记忆的描述
    existing_descriptions = []
    for i, mem in enumerate(existing_memories):
        existing_descriptions.append(f"[{i}] {mem['category']}: {mem['content']} ({', '.join(mem['keywords'])}")

    existing_memories_str = "\n".join(existing_descriptions) if existing_descriptions else "(none)"

    # 使用本地化的提示词
    system_prompt = await lang.text("conflict_detection.system_prompt", lang_str)
    user_prompt = await lang.text(
        "conflict_detection.user_prompt",
        lang_str,
        existing_memories=existing_memories_str,
        new_category=new_category,
        new_content=new_content,
        new_keywords=", ".join(new_keywords),
    )

    try:
        messages = [
            generate_message(system_prompt, "system"),
            generate_message(user_prompt, "user"),
        ]

        response = await fetch_message(messages, identify="Memory Conflict Detection")

        # 清理响应，移除可能的 markdown 代码块标记
        cleaned_response = re.sub(r"`{1,3}(json)?", "", response).strip()

        result = json.loads(cleaned_response)

        if result.get("has_conflict", False):
            conflict_indices = result.get("conflict_indices", [])
            # 验证索引范围
            valid_indices = [idx for idx in conflict_indices if 0 <= idx < len(existing_memories)]
            if valid_indices:
                logger.info(f"[InstantMemory] 检测到冲突: {result.get('reason', '无原因')}")
                logger.info(f"[InstantMemory] 冲突索引: {valid_indices}")
            return valid_indices

        return []
    except json.JSONDecodeError as e:
        logger.warning(f"[InstantMemory] LLM 冲突检测返回非 JSON 格式: {response}, 错误: {e}")
        return []
    except Exception as e:
        logger.exception(f"[InstantMemory] LLM 冲突检测失败: {e}")
        return []


async def post_instant_memory(
    category: Literal["myself", "emotion", "opinion", "goal", "activity"],
    content: str,
    keywords: list[str],
    expire_level: int,
    lang_str: str = "zh_tw",
    ctx_id: str = "",
    name: str = "",
) -> None:
    """
    post instant memory
    使用 LLM 检测并移除冲突的 memory

    Args:
        lang_str: 语言代码，用于本地化提示词
    """
    global instant_memories

    # 确保 expire_level 在 1-5 范围内
    expire_level = max(1, min(5, expire_level))

    # 使用 LLM 检测冲突
    conflict_indices = await detect_conflicts_with_llm(category, content, keywords, instant_memories, lang_str)

    # 移除冲突的记忆（从后往前删除以避免索引变化问题）
    if conflict_indices:
        for idx in sorted(conflict_indices, reverse=True):
            removed_mem = instant_memories.pop(idx)
            logger.info(f"[InstantMemory] 移除冲突记忆: {removed_mem['content'][:50]}...")

    instant_memories.append(
        {
            "category": category,
            "content": content,
            "keywords": keywords,
            "create_time": datetime.now(),
            "recall_level": 0,
            "expire_level": expire_level,
            "ctx_id": ctx_id,
            "name": name,
        }
    )

    logger.info(f"[InstantMemory] 添加新记忆: {content[:50]}...")


def filter_instant_memory(chat_history: str) -> Generator[InstantMemory, None, None]:
    for memory in instant_memories:
        if any(keyword in chat_history for keyword in memory["keywords"]):
            memory["recall_level"] += 1
            yield memory
    clear_expired_instant_memory()


def clear_expired_instant_memory() -> None:
    global instant_memories
    instant_memories = [memory for memory in instant_memories if _is_memory_valid(memory)]


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
