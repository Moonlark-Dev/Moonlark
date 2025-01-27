from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(name="nonebot_plugin_cave_get", description="", usage="")

require("nonebot_plugin_larkcave:comment")

import traceback
from nonebot.log import logger
from ...decoder import decode_cave
from ...models import CaveData
from ...__main__ import cave
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound
from ...lang import lang
from ..comment.message import add_cave_message
from ..comment.get import get_comments


@cave.assign("get.cave_id")
async def _(
    session: async_scoped_session, cave_id: int, user_id: str = get_user_id(), is_superuser: bool = is_user_superuser()
) -> None:
    try:
        cave_data = await session.get_one(CaveData, {"id": cave_id})
        content = await decode_cave(cave_data, session, user_id)
    except NoResultFound:
        await lang.finish("get.not_found", user_id, cave_id)
    if (not cave_data.public) and not is_superuser:
        await lang.finish("get.no_permission", user_id)
    if not ((cave_data.author == cave_data.author) or is_superuser):
        await lang.finish("get.no_permission", user_id)
    try:
        add_cave_message(cave_id, str((await content.send()).msg_ids[0]["message_id"]))
    except Exception:
        logger.error(f"写入回声洞消息队列时发生错误: {traceback.format_exc()}")
    if msg := await get_comments(cave_id, session, user_id):
        await msg.send()
    await cave.finish()

