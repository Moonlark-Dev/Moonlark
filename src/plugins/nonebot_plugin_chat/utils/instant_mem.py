from datetime import datetime, timedelta
from typing import TypedDict

from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot.log import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select, delete
import json
import re
import asyncio

from ..lang import lang
from ..models import InstantMemoryCache


class InstantMemory(TypedDict):
    content: str
    create_time: datetime
    expire_time: datetime
    ctx_id: str
    name: str


_deduplicate_lock = asyncio.Lock()

instant_memories: list[InstantMemory] = []


def _clear_expired() -> None:
    global instant_memories
    now = datetime.now()
    instant_memories = [mem for mem in instant_memories if mem["expire_time"] > now]


def get_instant_memories() -> list[InstantMemory]:
    _clear_expired()
    return instant_memories


def get_memories_for_display(current_session_id: str) -> list[InstantMemory]:
    """获取用于跨会话展示的记忆（排除当前会话今天的记忆）"""
    _clear_expired()
    now = datetime.now()
    today = now.date()
    return [
        mem
        for mem in instant_memories
        if not (mem["ctx_id"] == current_session_id and mem["create_time"].date() == today)
    ]


def get_memories_for_session(session_id: str) -> list[InstantMemory]:
    """获取指定会话的所有未过期记忆（用于上下文重置时注入）"""
    _clear_expired()
    return [mem for mem in instant_memories if mem["ctx_id"] == session_id]


async def load_memories_from_db() -> None:
    """从数据库加载所有未过期的即时记忆到内存"""
    global instant_memories
    try:
        now = datetime.now()
        async with get_session() as db_session:
            records = await db_session.scalars(
                select(InstantMemoryCache).where(InstantMemoryCache.expire_time > now)
            )
            loaded = [
                InstantMemory(
                    content=r.content,
                    create_time=r.created_time,
                    expire_time=r.expire_time,
                    ctx_id=r.session_id,
                    name=r.name,
                )
                for r in records
            ]

        # 合并：内存中已有的不覆盖，只补充 DB 中有但内存中没有的
        existing_keys = {(m["content"], m["ctx_id"]) for m in instant_memories}
        new_from_db = [m for m in loaded if (m["content"], m["ctx_id"]) not in existing_keys]
        instant_memories.extend(new_from_db)

        logger.info(f"[InstantMemory] 从数据库加载了 {len(new_from_db)} 条记忆（内存中共 {len(instant_memories)} 条）")
    except Exception as e:
        logger.warning(f"[InstantMemory] 从数据库加载记忆失败: {e}")


async def _save_memory_to_db(memory: InstantMemory) -> None:
    """将单条记忆保存到数据库"""
    try:
        async with get_session() as db_session:
            cache = InstantMemoryCache(
                session_id=memory["ctx_id"],
                content=memory["content"],
                name=memory.get("name", ""),
                created_time=memory["create_time"],
                expire_time=memory["expire_time"],
            )
            db_session.add(cache)
            await db_session.commit()
    except Exception as e:
        logger.warning(f"[InstantMemory] 保存记忆到数据库失败: {e}")


async def _cleanup_expired_db() -> None:
    """清理数据库中过期的记忆"""
    try:
        now = datetime.now()
        async with get_session() as db_session:
            await db_session.execute(
                delete(InstantMemoryCache).where(InstantMemoryCache.expire_time <= now)
            )
            await db_session.commit()
    except Exception as e:
        logger.warning(f"[InstantMemory] 清理过期记忆失败: {e}")


def format_memories_for_injection(memories: list[InstantMemory]) -> str:
    """将记忆列表格式化为注入消息队列的文本"""
    if not memories:
        return ""

    lines = ["以下是此前的即时记忆，帮助你了解之前发生的事情："]
    for mem in memories:
        time_str = mem["create_time"].strftime("%H:%M")
        name_part = f"[{mem['name']}] " if mem.get("name") else ""
        lines.append(f"- ({time_str}) {name_part}{mem['content']}")
    return "\n".join(lines)


async def post_instant_memory(
    content: str,
    expire_hours: float,
    lang_str: str = "zh_tw",
    ctx_id: str = "",
    name: str = "",
) -> None:
    global instant_memories

    expire_hours = min(16, max(0.1, expire_hours))

    memory: InstantMemory = {
        "content": content,
        "create_time": datetime.now(),
        "expire_time": datetime.now() + timedelta(hours=expire_hours),
        "ctx_id": ctx_id,
        "name": name,
    }
    instant_memories.append(memory)

    # 持久化到数据库
    await _save_memory_to_db(memory)

    logger.info(f"[InstantMemory] 添加新记忆: {content[:50]}...")


def delete_sleep_memory() -> None:
    global instant_memories
    instant_memories = [mem for mem in instant_memories if "睡觉" not in mem["content"]]
    logger.info("[InstantMemory] 已删除睡觉相关记忆")


async def _deduplicate(lang_str: str = "zh_tw") -> None:
    if _deduplicate_lock.locked():
        return

    async with _deduplicate_lock:
        _clear_expired()

        if len(instant_memories) <= 1:
            return

        try:
            memory_descriptions = []
            for i, mem in enumerate(instant_memories):
                create_str = mem["create_time"].strftime("%Y-%m-%d %H:%M:%S")
                memory_descriptions.append(f"[{i}] (创建于 {create_str}) {mem['content']}")
            existing_memories_str = "\n".join(memory_descriptions)

            system_prompt = await lang.text("conflict_detection.system_prompt", lang_str)
            user_prompt = await lang.text(
                "conflict_detection.user_prompt",
                lang_str,
                existing_memories=existing_memories_str,
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            messages = [
                generate_message(system_prompt, "system"),
                generate_message(user_prompt, "user"),
            ]

            response = await fetch_message(messages, identify="Memory Deduplication")
            cleaned_response = re.sub(r"`{1,3}(json)?", "", response).strip()
            result = json.loads(cleaned_response)

            valid_indices = result.get("valid_indices", [])
            valid_set = {idx for idx in valid_indices if 0 <= idx < len(instant_memories)}

            if len(valid_set) < len(instant_memories):
                new_memories = [mem for i, mem in enumerate(instant_memories) if i in valid_set]
                removed_count = len(instant_memories) - len(new_memories)
                instant_memories[:] = new_memories
                if removed_count > 0:
                    logger.info(f"[InstantMemory] 筛选完成: 保留 {len(valid_set)} 条，移除 {removed_count} 条")

        except json.JSONDecodeError as e:
            logger.warning(f"[InstantMemory] LLM 筛选返回非 JSON 格式: {e}")
        except Exception as e:
            logger.exception(f"[InstantMemory] LLM 筛选失败: {e}")


class InstantMemoryManager:
    def __init__(self, session_id: str, lang_str: str = "zh_tw") -> None:
        self.session_id = session_id
        self.lang_str = lang_str
        self.message_cache: list[str] = []
        self.cursor: int = 0
        self._generate_lock = asyncio.Lock()

    def add_messages_to_cache(self, messages: list[str]) -> None:
        self.message_cache.extend(messages)
        logger.debug(f"[InstantMemory:{self.session_id}] 缓存消息数量: {len(self.message_cache)}")

    def should_generate(self) -> bool:
        return len(self.message_cache) >= 25

    async def generate(self) -> list[InstantMemory]:
        global instant_memories

        if self._generate_lock.locked():
            return []

        async with self._generate_lock:
            if not self.message_cache:
                return []

            messages_to_process = self.message_cache.copy()
            self.message_cache.clear()

            try:
                model_response = await fetch_message(
                    [
                        generate_message(
                            await lang.text("memory_cache.creator", self.lang_str, datetime.now().isoformat()),
                            "system",
                        ),
                        generate_message("\n".join(messages_to_process), "user"),
                    ],
                    reasoning_effort="medium",
                )

                memory_list = json.loads(re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", model_response))

                new_memories = []
                for mem in memory_list:
                    expire_hours = mem.get("expire_hours", 1)
                    expire_hours = min(16, max(0.1, expire_hours))

                    memory: InstantMemory = {
                        "content": mem["content"],
                        "create_time": datetime.now(),
                        "expire_time": datetime.now() + timedelta(hours=expire_hours),
                        "ctx_id": self.session_id,
                        "name": mem.get("name", ""),
                    }
                    new_memories.append(memory)
                    # 持久化每条记忆
                    await _save_memory_to_db(memory)

                instant_memories.extend(new_memories)
                logger.info(f"[InstantMemory:{self.session_id}] 生成了 {len(new_memories)} 条即时记忆")

                await _deduplicate(self.lang_str)

                return new_memories

            except Exception as e:
                logger.exception(f"[InstantMemory:{self.session_id}] 生成即时记忆失败: {e}")
                return []
