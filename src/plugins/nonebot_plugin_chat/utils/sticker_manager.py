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

import base64
import json
import re
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

from nonebot import logger
from nonebot_plugin_orm import get_session
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from sqlalchemy import select

from ..models import Sticker
from .sticker_similarity import calculate_hash_async, check_sticker_duplicate


# 表情包分类结果类型
class MemeClassification(TypedDict):
    is_meme: bool
    text: str
    emotion: str
    labels: List[str]
    context_keywords: List[str]


# 表情包分类提示词
MEME_CLASSIFICATION_PROMPT = """你是一个表情包分析 AI。
我会向你提供一张表情包图片，你需要分析表情包的内容，并对其进行分类。
  
### 输出格式
一段 JSON，不要包含除了 JSON 结构以外的任何内容。
  
{
     "is_meme": boolen,       // 这张图片是一个表情包吗？如果是为 true。
     "text": string,                 // 表情包中的文本，如果没有请填空字符串。
     "emotion": string,        // 表情包所表达的情绪的类型，如：高兴、难过、生气、恐惧。
     "labels": array[string],       // 表情包的标签，按照参考的标签库分类中给出的示例进行编写。
     "context_keywords": array[string]       // 表情包适用的语境，这个表情包适合在群聊中谈到什么关键词时出现？
}
  
### 参考的标签库分类
1.  **社交回应类**：`赞同`、`反对`、`无语`、`震惊`、`委屈`、`认怂`。
2.  **网络梗类**：`吃瓜`、`摆烂`、`摸鱼`、`内卷`、`抽象`、`典`。
3.  **时间/天气类**：`早安`、`周五`、`放假`。
4.  **互动类**：`贴贴`、`抱抱`、`禁言`、`反弹`。"""


def extract_json_from_response(response: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 响应中提取 JSON，处理可能包含 markdown 代码块的情况

    Args:
        response: LLM 返回的原始响应文本

    Returns:
        解析后的 JSON 字典，如果解析失败返回 None
    """
    # 去除首尾空白
    response = response.strip()

    # 尝试直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 尝试提取 markdown 代码块中的 JSON
    # 匹配 ```json ... ``` 或 ``` ... ```
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(code_block_pattern, response)

    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # 尝试查找 JSON 对象（以 { 开头，以 } 结尾）
    json_pattern = r"\{[\s\S]*\}"
    json_matches = re.findall(json_pattern, response)

    for match in json_matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    return None


async def classify_meme(image_data: bytes) -> Optional[MemeClassification]:
    """
    使用 LLM 对表情包进行分类

    Args:
        image_data: 图片二进制数据

    Returns:
        MemeClassification 分类结果，如果分类失败返回 None
    """
    try:
        # 转换图片为 base64
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # 构建消息
        messages = [
            generate_message(MEME_CLASSIFICATION_PROMPT, "system"),
            generate_message(
                [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": "请分析这张图片并输出分类 JSON。"},
                ],
                "user",
            ),
        ]

        # 调用 LLM
        response = (await fetch_message(messages, identify="Meme Classification")).strip()

        # 解析 JSON（处理可能的 markdown 代码块）
        result = extract_json_from_response(response)

        if result is None:
            logger.warning(f"Failed to parse meme classification response: {response}")
            return None

        # 验证并转换结果
        classification: MemeClassification = {
            "is_meme": bool(result.get("is_meme", False)),
            "text": str(result.get("text", "")),
            "emotion": str(result.get("emotion", "")),
            "labels": list(result.get("labels", [])),
            "context_keywords": list(result.get("context_keywords", [])),
        }

        return classification

    except Exception as e:
        logger.warning(f"Failed to classify meme: {e}\n{traceback.format_exc()}")
        return None


class DuplicateStickerError(Exception):
    """表情包重复异常"""

    def __init__(self, existing_sticker: Sticker, similarity: float):
        self.existing_sticker = existing_sticker
        self.similarity = similarity
        super().__init__(f"发现重复的表情包 (ID: {existing_sticker.id}, 相似度: {similarity:.2%})")


class NotMemeError(Exception):
    """图片不是表情包异常"""

    def __init__(self, message: str = "该图片不是表情包"):
        self.message = message
        super().__init__(message)


class StickerManager:
    """Sticker management system for saving, searching and retrieving stickers"""

    async def save_sticker(
        self, description: str, raw: bytes, group_id: Optional[str] = None, check_duplicate: bool = True
    ) -> Sticker:
        """
        Save a sticker to the database

        Args:
            description: VLM-generated description of the sticker
            raw: Binary image data
            group_id: Source group ID (optional, for tracking origin)
            check_duplicate: Whether to check for duplicate stickers (default: True)

        Returns:
            The created Sticker object

        Raises:
            DuplicateStickerError: If a duplicate sticker is found
        """
        current_time = datetime.now()

        async with get_session() as session:
            # 检查重复
            if check_duplicate:
                is_duplicate, existing_sticker, similarity = await check_sticker_duplicate(raw, session)
                if is_duplicate and existing_sticker:
                    raise DuplicateStickerError(existing_sticker, similarity)

            # 计算感知哈希
            p_hash = await calculate_hash_async(raw)

            # 调用 LLM 进行表情包分类
            classification = await classify_meme(raw)

            # 准备分类数据
            meme_text: Optional[str] = None
            emotion: Optional[str] = None
            labels_json: Optional[str] = None
            context_keywords_json: Optional[str] = None

            if classification is not None:
                # 如果不是表情包，拒绝添加
                if not classification["is_meme"]:
                    raise NotMemeError("该图片不是表情包，无法收藏")

                meme_text = classification["text"]
                emotion = classification["emotion"]
                labels_json = json.dumps(classification["labels"], ensure_ascii=False)
                context_keywords_json = json.dumps(classification["context_keywords"], ensure_ascii=False)

            sticker = Sticker(
                description=description,
                raw=raw,
                group_id=group_id,
                created_time=current_time.timestamp(),
                p_hash=p_hash if p_hash else None,
                meme_text=meme_text,
                emotion=emotion,
                labels=labels_json,
                context_keywords=context_keywords_json,
            )

            session.add(sticker)
            await session.commit()
            await session.refresh(sticker)

        return sticker

    async def search_sticker(self, query: str, limit: int = 5) -> List[Sticker]:
        """
        Search stickers by description (fuzzy matching)
        Searches across ALL stickers globally, regardless of group_id

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        async with get_session() as session:
            # Use LIKE for fuzzy matching on description
            # Split query into keywords for better matching
            keywords = query.split()

            # Build query - search globally across all stickers
            stmt = select(Sticker)

            # Apply keyword filters using LIKE
            for keyword in keywords:
                stmt = stmt.where(Sticker.description.contains(keyword))

            # Order by created_time descending (newest first) and limit results
            stmt = stmt.order_by(Sticker.created_time.desc()).limit(limit)

            result = await session.scalars(stmt)
            return list(result.all())

    async def search_sticker_any(self, query: str, limit: int = 5) -> List[Sticker]:
        """
        Search stickers matching ANY keyword (OR logic)
        Searches across ALL stickers globally

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        from sqlalchemy import or_

        async with get_session() as session:
            keywords = query.split()

            if not keywords:
                return []

            # Build OR conditions for each keyword
            conditions = [Sticker.description.contains(keyword) for keyword in keywords]

            stmt = select(Sticker).where(or_(*conditions)).order_by(Sticker.created_time.desc()).limit(limit)

            result = await session.scalars(stmt)
            return list(result.all())

    async def get_sticker(self, sticker_id: int) -> Optional[Sticker]:
        """
        Get a sticker by its ID

        Args:
            sticker_id: The ID of the sticker to retrieve

        Returns:
            The Sticker object if found, None otherwise
        """
        async with get_session() as session:
            return await session.get(Sticker, sticker_id)

    async def delete_sticker(self, sticker_id: int) -> bool:
        """
        Delete a sticker by its ID

        Args:
            sticker_id: The ID of the sticker to delete

        Returns:
            True if deleted, False if not found
        """
        async with get_session() as session:
            sticker = await session.get(Sticker, sticker_id)
            if not sticker:
                return False

            await session.delete(sticker)
            await session.commit()
            return True

    async def get_all_stickers(self, limit: int = 100) -> List[Sticker]:
        """
        Get all stickers (for listing purposes)

        Args:
            limit: Maximum number of stickers to return

        Returns:
            List of Sticker objects
        """
        async with get_session() as session:
            stmt = select(Sticker).order_by(Sticker.created_time.desc()).limit(limit)
            result = await session.scalars(stmt)
            return list(result.all())

    async def filter_by_emotion(self, emotion: str, limit: int = 10) -> List[Sticker]:
        """
        Filter stickers by emotion

        Args:
            emotion: Emotion to filter by (e.g., "高兴", "难过", "生气")
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        async with get_session() as session:
            stmt = (
                select(Sticker)
                .where(Sticker.emotion.contains(emotion))
                .order_by(Sticker.created_time.desc())
                .limit(limit)
            )
            result = await session.scalars(stmt)
            return list(result.all())

    async def filter_by_label(self, label: str, limit: int = 10) -> List[Sticker]:
        """
        Filter stickers by label (searches within JSON array)

        Args:
            label: Label to filter by (e.g., "赞同", "摆烂", "贴贴")
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        async with get_session() as session:
            # labels 字段是 JSON 数组字符串，使用 contains 进行模糊匹配
            stmt = (
                select(Sticker).where(Sticker.labels.contains(label)).order_by(Sticker.created_time.desc()).limit(limit)
            )
            result = await session.scalars(stmt)
            return list(result.all())

    async def filter_by_context_keyword(self, keyword: str, limit: int = 10) -> List[Sticker]:
        """
        Filter stickers by context keyword (searches within JSON array)

        Args:
            keyword: Context keyword to filter by
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        async with get_session() as session:
            # context_keywords 字段是 JSON 数组字符串，使用 contains 进行模糊匹配
            stmt = (
                select(Sticker)
                .where(Sticker.context_keywords.contains(keyword))
                .order_by(Sticker.created_time.desc())
                .limit(limit)
            )
            result = await session.scalars(stmt)
            return list(result.all())

    async def filter_by_classification(
        self,
        emotion: Optional[str] = None,
        labels: Optional[List[str]] = None,
        context_keywords: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Sticker]:
        """
        Filter stickers by multiple classification criteria (AND logic)

        Args:
            emotion: Emotion to filter by (optional)
            labels: List of labels to filter by, all must match (optional)
            context_keywords: List of context keywords to filter by, all must match (optional)
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        async with get_session() as session:
            stmt = select(Sticker)

            # 应用情绪筛选
            if emotion:
                stmt = stmt.where(Sticker.emotion.contains(emotion))

            # 应用标签筛选（所有标签都必须匹配）
            if labels:
                for label in labels:
                    stmt = stmt.where(Sticker.labels.contains(label))

            # 应用语境关键词筛选（所有关键词都必须匹配）
            if context_keywords:
                for keyword in context_keywords:
                    stmt = stmt.where(Sticker.context_keywords.contains(keyword))

            stmt = stmt.order_by(Sticker.created_time.desc()).limit(limit)
            result = await session.scalars(stmt)
            return list(result.all())

    async def migrate_existing_stickers(self, batch_size: int = 10) -> Dict[str, int]:
        """
        Migrate existing stickers by classifying them with LLM

        This method processes stickers that don't have classification data
        (meme_text, emotion, labels, context_keywords are all None)

        Args:
            batch_size: Number of stickers to process in each batch

        Returns:
            Dict with migration statistics:
            - total: Total number of stickers processed
            - success: Number of successfully classified stickers
            - failed: Number of stickers that failed classification
            - skipped: Number of stickers already classified
        """
        stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        async with get_session() as session:
            # 查找所有未分类的表情包（分类字段都为 None）
            stmt = select(Sticker).where(
                Sticker.meme_text.is_(None),
                Sticker.emotion.is_(None),
                Sticker.labels.is_(None),
                Sticker.context_keywords.is_(None),
            )
            result = await session.scalars(stmt)
            stickers_to_migrate = list(result.all())

            stats["total"] = len(stickers_to_migrate)

            for sticker in stickers_to_migrate:
                try:
                    # 调用 LLM 进行分类
                    classification = await classify_meme(sticker.raw)

                    if classification is None:
                        logger.warning(f"Failed to classify sticker {sticker.id}: LLM returned None")
                        stats["failed"] += 1
                        continue

                    # 更新分类信息
                    sticker.meme_text = classification["text"]
                    sticker.emotion = classification["emotion"]
                    sticker.labels = json.dumps(classification["labels"], ensure_ascii=False)
                    sticker.context_keywords = json.dumps(classification["context_keywords"], ensure_ascii=False)

                    session.add(sticker)
                    stats["success"] += 1

                    logger.info(f"Successfully classified sticker {sticker.id}: emotion={classification['emotion']}")

                except Exception as e:
                    logger.warning(f"Failed to migrate sticker {sticker.id}: {e}")
                    stats["failed"] += 1

            # 提交所有更改
            await session.commit()

        logger.info(
            f"Sticker migration completed: {stats['success']} success, "
            f"{stats['failed']} failed, {stats['skipped']} skipped out of {stats['total']} total"
        )

        return stats

    async def classify_single_sticker(self, sticker_id: int) -> bool:
        """
        Classify a single sticker by its ID

        Args:
            sticker_id: The ID of the sticker to classify

        Returns:
            True if classification was successful, False otherwise
        """
        async with get_session() as session:
            sticker = await session.get(Sticker, sticker_id)

            if sticker is None:
                logger.warning(f"Sticker {sticker_id} not found")
                return False

            try:
                classification = await classify_meme(sticker.raw)

                if classification is None:
                    logger.warning(f"Failed to classify sticker {sticker_id}: LLM returned None")
                    return False

                sticker.meme_text = classification["text"]
                sticker.emotion = classification["emotion"]
                sticker.labels = json.dumps(classification["labels"], ensure_ascii=False)
                sticker.context_keywords = json.dumps(classification["context_keywords"], ensure_ascii=False)

                session.add(sticker)
                await session.commit()

                logger.info(f"Successfully classified sticker {sticker_id}")
                return True

            except Exception as e:
                logger.warning(f"Failed to classify sticker {sticker_id}: {e}")
                return False


# Global sticker manager instance
sticker_manager = StickerManager()


def get_sticker_manager() -> StickerManager:
    """
    Get the global StickerManager instance

    Returns:
        StickerManager instance
    """
    return sticker_manager
