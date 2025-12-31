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

from typing import TYPE_CHECKING, List

from nonebot_plugin_alconna import UniMessage

from ...lang import lang
from ..image import get_image_by_id
from ..sticker_manager import get_sticker_manager

if TYPE_CHECKING:
    from ...matcher.group import GroupSession


async def save_sticker_func(session: "GroupSession", image_id: str) -> str:
    """
    Save an image as a sticker

    Args:
        session: The group session
        image_id: Temporary image ID from the message context

    Returns:
        Success or error message
    """
    # Get image data from cache
    image_data = await get_image_by_id(image_id)

    if image_data is None:
        return await lang.text("sticker.not_found", session.user_id)

    # Get sticker manager and save
    manager = await get_sticker_manager()
    sticker = await manager.save_sticker(
        description=image_data["description"],
        raw=image_data["raw"],
        group_id=session.group_id,
    )

    return await lang.text("sticker.saved", session.user_id, sticker.id)


async def search_sticker_func(session: "GroupSession", query: str) -> str:
    """
    Search for stickers by description

    Args:
        session: The group session
        query: Search query string

    Returns:
        Formatted list of matching stickers or empty message
    """
    manager = await get_sticker_manager()

    # First try AND matching (all keywords must match)
    stickers = await manager.search_sticker(query, limit=5)

    # If no results, try OR matching (any keyword matches)
    if not stickers:
        stickers = await manager.search_sticker_any(query, limit=5)

    if not stickers:
        return await lang.text("sticker.search_empty", session.user_id)

    # Format results
    results = []
    for sticker in stickers:
        # Truncate description if too long
        desc = sticker.description
        if len(desc) > 50:
            desc = desc[:47] + "..."
        results.append(f"- {sticker.id}: {desc}")

    return await lang.text("sticker.search_result", session.user_id, "\n".join(results))


async def send_sticker_func(session: "GroupSession", sticker_id: int) -> str:
    """
    Send a sticker to the group

    Args:
        session: The group session
        sticker_id: Database ID of the sticker to send

    Returns:
        Success or error message
    """
    manager = await get_sticker_manager()
    sticker = await manager.get_sticker(sticker_id)

    if sticker is None:
        return await lang.text("sticker.id_not_found", session.user_id, sticker_id)

    try:
        # Create and send the image message
        message = UniMessage.image(raw=sticker.raw)
        await message.send(target=session.target, bot=session.bot)
        return await lang.text("sticker.sent", session.user_id)
    except Exception as e:
        return await lang.text("sticker.send_failed", session.user_id, str(e))


def get_sticker_tools(session: "GroupSession") -> List:
    """
    Get sticker-related tool functions for the LLM

    Args:
        session: The group session

    Returns:
        List of AsyncFunction objects for sticker tools
    """
    from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter

    async def save_sticker(image_id: str) -> str:
        return await save_sticker_func(session, image_id)

    async def search_sticker(query: str) -> str:
        return await search_sticker_func(session, query)

    async def send_sticker(sticker_id: int) -> str:
        return await send_sticker_func(session, sticker_id)

    return [
        AsyncFunction(
            func=save_sticker,
            description=(
                "将当前对话中出现的一张图片收藏为表情包。\n"
                "**何时调用**: 当你觉得群友发的某张图片很有趣、很有表情包价值时，可以主动收藏它。\n"
                "**注意**: 只能收藏当前对话中出现的图片，使用消息中标注的图片 ID。"
            ),
            parameters={
                "image_id": FunctionParameter(
                    type="string",
                    description="要收藏的图片的临时 ID，格式如 'img_1'，从消息中的 [图片(ID:xxx): 描述] 中获取。",
                    required=True,
                ),
            },
        ),
        AsyncFunction(
            func=search_sticker,
            description=(
                "从收藏的表情包库中搜索合适的表情包。\n"
                "**何时调用**: 当你想用表情包回复群友时，先调用此工具搜索合适的表情包。\n"
                "**搜索技巧**: 使用描述性的关键词，如情绪（开心、悲伤、嘲讽）、动作（大笑、哭泣）或内容（猫、狗、熊猫头）。"
            ),
            parameters={
                "query": FunctionParameter(
                    type="string",
                    description="搜索关键词，可以是情绪、动作、内容等描述性词语，多个关键词用空格分隔。",
                    required=True,
                ),
            },
        ),
        AsyncFunction(
            func=send_sticker,
            description=(
                "发送一个已收藏的表情包到群聊中。\n"
                "**何时调用**: 在使用 search_sticker 找到合适的表情包后，调用此工具发送。\n"
                "**注意**: sticker_id 必须是从 search_sticker 结果中获得的有效 ID。"
            ),
            parameters={
                "sticker_id": FunctionParameter(
                    type="integer",
                    description="要发送的表情包的数据库 ID，从 search_sticker 的搜索结果中获取。",
                    required=True,
                ),
            },
        ),
    ]
