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

import time
import math
import random
from collections import Counter
from typing import List, Tuple, Dict, Any

from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select, delete

from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message

from ..models import MemoryNode, MemoryEdge


def calculate_information_content(text: str) -> float:
    """计算文本的信息量（熵）"""
    char_count = Counter(text)
    total_chars = len(text)
    if total_chars == 0:
        return 0
    entropy = 0
    for count in char_count.values():
        probability = count / total_chars
        entropy -= probability * math.log2(probability)
    return entropy


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """计算余弦相似度"""
    import math

    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0
    return dot_product / (norm1 * norm2)


async def extract_topics_from_text(text: str, max_topics: int = 5) -> List[str]:
    prompt = (
        f"这是一段文字：\n{text}\n\n请你从这段话中总结出最多{max_topics}个关键的概念，必须是某种概念，比如人，事，物，概念，事件，地点 等等，帮我列出来，"
        f"将主题用逗号隔开，并加上<>,例如<主题1>,<主题2>......尽可能精简。只需要列举最多{max_topics}个话题就好，不要有序号，不要告诉我其他内容。"
        f"如果确定找不出主题或者没有明显主题，返回<none>。"
    )
    result = await fetch_message([generate_message(prompt, "user")])
    if result == "<none>":
        return []
    return [i[1:-1] for i in result.split(",")]


async def _integrate_memories_with_llm(existing_memory: str, new_memory: str) -> str:
    """使用LLM整合新旧记忆"""
    try:
        integration_prompt = f"""你是一个记忆整合专家。请将以下的旧记忆和新记忆整合成一条更完整、更准确的记忆内容。

旧记忆内容：
{existing_memory}

新记忆内容：
{new_memory}

整合要求：
1. 保留重要信息，去除重复内容
2. 如果新旧记忆有冲突，合理整合矛盾的地方
3. 将相关信息合并，形成更完整的描述
4. 保持语言简洁、准确
5. 只返回整合后的记忆内容，不要添加任何解释

整合后的记忆："""

        content = await fetch_message([generate_message(integration_prompt, "user")])

        if content and content.strip():
            return content.strip()
        else:
            return f"{existing_memory} | {new_memory}"

    except Exception as e:
        logger.exception(e)
        return f"{existing_memory} | {new_memory}"


class MemoryGraph:
    """基于图的记忆系统，适配自MaiBot的实现"""

    def __init__(self, context_id: str):
        self.context_id = context_id  # 可以是 user_id 或 group_id
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[Tuple[str, str], Dict[str, Any]] = {}

    async def load_from_db(self) -> None:
        """从数据库加载记忆图"""
        async with get_session() as session:
            # 加载节点
            nodes = await session.scalars(select(MemoryNode).where(MemoryNode.context_id == self.context_id))
            for node in nodes:
                self.nodes[node.concept] = {
                    "memory_items": node.memory_items,
                    "weight": node.weight,
                    "created_time": node.created_time,
                    "last_modified": node.last_modified,
                    "hash_value": node.hash_value,
                }

            # 加载边
            edges = await session.scalars(select(MemoryEdge).where(MemoryEdge.context_id == self.context_id))
            for edge in edges:
                self.edges[(edge.source, edge.target)] = {
                    "strength": edge.strength,
                    "created_time": edge.created_time,
                    "last_modified": edge.last_modified,
                    "hash_value": edge.hash_value,
                }

    async def save_to_db(self) -> None:
        """将记忆图保存到数据库"""
        async with get_session() as session:
            # 清除旧数据
            await session.execute(delete(MemoryNode).where(MemoryNode.context_id == self.context_id))
            await session.execute(delete(MemoryEdge).where(MemoryEdge.context_id == self.context_id))

            # 保存节点
            for concept, data in self.nodes.items():
                node = MemoryNode(
                    concept=concept,
                    context_id=self.context_id,
                    memory_items=data["memory_items"],
                    weight=data["weight"],
                    created_time=data["created_time"],
                    last_modified=data["last_modified"],
                    hash_value=data["hash_value"],
                )
                session.add(node)

            # 保存边
            for (source, target), data in self.edges.items():
                edge = MemoryEdge(
                    source=source,
                    target=target,
                    context_id=self.context_id,
                    strength=data["strength"],
                    created_time=data["created_time"],
                    last_modified=data["last_modified"],
                    hash_value=data["hash_value"],
                )
                session.add(edge)

            await session.commit()

    def connect_concepts(self, concept1: str, concept2: str) -> None:
        """连接两个概念"""
        if concept1 == concept2:
            return

        current_time = time.time()
        edge_key = (concept1, concept2)

        if edge_key in self.edges:
            self.edges[edge_key]["strength"] += 1
            self.edges[edge_key]["last_modified"] = current_time
        else:
            self.edges[edge_key] = {
                "strength": 1,
                "created_time": current_time,
                "last_modified": current_time,
                "hash_value": hash((concept1, concept2)),
            }

    async def add_memory_to_concept(self, concept: str, memory: str) -> None:
        """为概念添加记忆"""
        current_time = time.time()

        if concept in self.nodes:
            existing_memory = self.nodes[concept]["memory_items"]
            if existing_memory and existing_memory.strip():
                # 使用LLM整合新旧记忆
                integrated_memory = await _integrate_memories_with_llm(existing_memory, memory)
                self.nodes[concept]["memory_items"] = integrated_memory
                self.nodes[concept]["weight"] += 1.0
            else:
                self.nodes[concept]["memory_items"] = memory
            self.nodes[concept]["last_modified"] = current_time
        else:
            self.nodes[concept] = {
                "memory_items": memory,
                "weight": 1.0,
                "created_time": current_time,
                "last_modified": current_time,
                "hash_value": hash(f"{concept}:{memory}"),
            }

    def get_related_memories(self, topic: str, max_depth: int = 2) -> List[Tuple[str, str]]:
        """获取相关记忆"""
        if topic not in self.nodes:
            return []

        memories = []
        visited = set()

        # 获取直接记忆
        node_data = self.nodes[topic]
        if node_data["memory_items"]:
            memories.append((topic, node_data["memory_items"]))
            visited.add(topic)

        # 获取相邻节点的记忆
        if max_depth > 1:
            for (source, target), _ in self.edges.items():
                related_concept = None
                if source == topic and target not in visited:
                    related_concept = target
                elif target == topic and source not in visited:
                    related_concept = source

                if related_concept and related_concept in self.nodes:
                    related_data = self.nodes[related_concept]
                    if related_data["memory_items"]:
                        memories.append((related_concept, related_data["memory_items"]))
                        visited.add(related_concept)

        return memories

    def forget_random_memories(self, forget_ratio: float = 0.1) -> int:
        """随机遗忘一些记忆"""
        current_time = time.time()
        forgotten_count = 0

        # 遗忘老旧的节点
        nodes_to_remove = []
        for concept, data in self.nodes.items():
            time_diff = current_time - data["last_modified"]
            # 基于权重调整遗忘阈值
            forget_threshold = 3600 * 24 * 3 * data["weight"]

            if time_diff > forget_threshold and random.random() < forget_ratio:
                nodes_to_remove.append(concept)

        for concept in nodes_to_remove:
            del self.nodes[concept]
            forgotten_count += 1
            # 同时删除相关的边
            edges_to_remove = [(s, t) for (s, t) in self.edges if s == concept or t == concept]
            for edge in edges_to_remove:
                del self.edges[edge]

        # 遗忘弱连接
        edges_to_remove = []
        for edge_key, edge_data in self.edges.items():
            time_diff = current_time - edge_data["last_modified"]
            if time_diff > 3600 * 24 * 3 and edge_data["strength"] <= 1:  # 3天内的弱连接
                if random.random() < forget_ratio:
                    edges_to_remove.append(edge_key)

        for edge in edges_to_remove:
            del self.edges[edge]

        return forgotten_count

    async def build_memory_from_text(self, text: str, compress_rate: float = 0.1) -> None:
        """从文本构建记忆"""
        # 计算主题数量
        topic_num = max(1, min(5, int(len(text) * compress_rate / 10)))

        # 提取主题
        topics = await extract_topics_from_text(text, topic_num)

        if not topics:
            return

        # 为每个主题生成摘要
        for topic in topics:
            try:
                summary_prompt = f"""这是一段文字：
{text}

请基于这段文字来概括"{topic}"这个概念，帮我总结成几句自然的话，要求包含对这个概念的定义、内容、知识，这些信息必须来自这段文字。只输出几句自然的话就好。"""

                summary = await fetch_message([generate_message(summary_prompt, "user")])

                if summary and summary.strip():
                    await self.add_memory_to_concept(topic, summary.strip())

            except Exception as e:
                logger.exception(e)
                await self.add_memory_to_concept(topic, f"关于{topic}的记忆：{text[:100]}...")

        # 连接相关概念
        for i, topic1 in enumerate(topics):
            for topic2 in topics[i + 1 :]:
                self.connect_concepts(topic1, topic2)


async def cleanup_old_memories(context_id: str, forget_ratio: float = 0.1) -> int:
    """清理旧记忆的公共接口"""
    memory_graph = MemoryGraph(context_id)
    await memory_graph.load_from_db()
    forgotten_count = memory_graph.forget_random_memories(forget_ratio)
    if forgotten_count > 0:
        await memory_graph.save_to_db()
    return forgotten_count
