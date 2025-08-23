#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

import json
import random
from typing import List, Tuple, Dict, Any

from nonebot import logger

try:
    from json_repair import repair_json
except ImportError:

    def repair_json(json_str: str) -> str:
        """Fallback implementation when json_repair is not available"""
        return json_str


from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message

from .memory_graph import MemoryGraph

from .memory_graph import extract_topics_from_text


def _calculate_relevance(keyword: str, target_message: str, memory_content: str) -> float:
    """计算记忆相关性（简化版）"""
    keyword_in_message = 1.0 if keyword.lower() in target_message.lower() else 0.0
    keyword_in_memory = 1.0 if keyword.lower() in memory_content.lower() else 0.0

    # 计算文本长度匹配度
    length_similarity = min(len(target_message), len(memory_content)) / max(
        len(target_message), len(memory_content)
    )

    return (keyword_in_message + keyword_in_memory + length_similarity) / 3.0


async def _select_memories_with_llm(
        target_message: str, chat_history: str, candidate_memories: List[Dict[str, Any]], max_memories: int
) -> List[Tuple[str, str]]:
    """使用LLM选择最相关的记忆"""
    try:
        # 构建记忆信息
        memory_lines = []
        for memory in candidate_memories:
            memory_id = memory["memory_id"]
            concept = memory["concept"]
            content = memory["content"]
            memory_lines.append(f"记忆编号 {memory_id}: [概念: {concept}] {content}")

        memory_info = "\n".join(memory_lines)

        # 构建选择提示
        selection_prompt = f"""你需要根据以下信息来挑选合适的记忆编号。

当前消息: {target_message}

聊天上下文:
{chat_history}

可用记忆:
{memory_info}

请从上述记忆中选择最多{max_memories}个与当前消息最相关的记忆，并输出一个JSON格式的响应：

{{
"memory_ids": "记忆1编号,记忆2编号,记忆3编号"
}}

只输出JSON格式，不要添加其他解释。"""

        # 调用LLM
        response = await fetch_message([generate_message(selection_prompt, "user")])

        # 解析响应
        try:
            fixed_json = repair_json(response)
            result = json.loads(fixed_json) if isinstance(fixed_json, str) else fixed_json
            memory_ids_str = result.get("memory_ids", "")

            if memory_ids_str:
                memory_ids = [mid.strip() for mid in str(memory_ids_str).split(",") if mid.strip()]
                valid_memory_ids = [mid for mid in memory_ids if mid and len(mid) <= 3]
            else:
                valid_memory_ids = []

        except Exception as e:
            # 解析失败，使用前几个记忆
            logger.exception(e)
            valid_memory_ids = [mem["memory_id"] for mem in candidate_memories[:max_memories]]

        # 根据ID筛选记忆
        memory_id_to_memory = {mem["memory_id"]: mem for mem in candidate_memories}
        selected_memories = []

        for memory_id in valid_memory_ids:
            if memory_id in memory_id_to_memory:
                memory = memory_id_to_memory[memory_id]
                selected_memories.append((memory["concept"], memory["content"]))

        # 如果没有选择到记忆，返回相关性最高的几个
        if not selected_memories:
            candidate_memories.sort(key=lambda x: x["relevance"], reverse=True)
            selected_memories = [(mem["concept"], mem["content"]) for mem in candidate_memories[:max_memories]]

        return selected_memories

    except Exception as e:
        logger.exception(e)
        # 出错时返回相关性最高的记忆
        candidate_memories.sort(key=lambda x: x["relevance"], reverse=True)
        return [(mem["concept"], mem["content"]) for mem in candidate_memories[:max_memories]]


async def activate_memories_from_text(
        context_id: str, target_message: str, chat_history: str = "", max_memories: int = 5
) -> List[Tuple[str, str]]:
    """
    从文本中激活相关记忆

    Args:
        context_id: 上下文ID（私聊为user_id，群聊为group_id）
        target_message: 目标消息
        chat_history: 聊天历史上下文
        max_memories: 最大返回记忆数量

    Returns:
        List[Tuple[str, str]]: 激活的记忆列表，格式为 (concept, memory_content)
    """
    # 加载记忆图
    memory_graph = MemoryGraph(context_id)
    await memory_graph.load_from_db()

    if not memory_graph.nodes:
        return []

    # 从目标消息中提取关键词
    keywords = await extract_topics_from_text(target_message)

    # 如果有聊天历史，也提取关键词
    if chat_history:
        history_keywords = await extract_topics_from_text(chat_history)
        keywords.extend(history_keywords)

    # 去重并限制关键词数量
    keywords = list(set(keywords))[:10]

    if not keywords:
        return []

    # 收集候选记忆
    candidate_memories = []
    used_ids = set()

    for keyword in keywords:
        related_memories = memory_graph.get_related_memories(keyword, max_depth=2)
        for concept, memory_content in related_memories:
            if memory_content and concept not in used_ids:
                # 分配随机ID用于LLM选择
                memory_id = f"{random.randint(10, 99):02d}"
                while memory_id in used_ids:
                    memory_id = f"{random.randint(10, 99):02d}"

                candidate_memories.append(
                    {
                        "memory_id": memory_id,
                        "concept": concept,
                        "content": memory_content,
                        "relevance": _calculate_relevance(keyword, target_message, memory_content),
                    }
                )
                used_ids.add(concept)

    if not candidate_memories:
        return []

    # 如果候选记忆较少，直接返回
    if len(candidate_memories) <= 2:
        return [(mem["concept"], mem["content"]) for mem in candidate_memories]

    # 使用LLM选择最相关的记忆
    selected_memories = await _select_memories_with_llm(
        target_message, chat_history, candidate_memories, max_memories
    )

    return selected_memories

#
# class MemoryActivator:
#     """记忆激活器，基于MaiBot的实现"""
#
#     def __init__(self):
#         pass
#
#
# # 全局记忆激活器实例
# memory_activator = MemoryActivator()
