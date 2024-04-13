from ...__main__ import cave
from ....nonebot_plugin_larkutils import get_user_id, is_superuser
from ...lang import lang
from ...model import CaveData
from nonebot_plugin_orm import async_scoped_session
from .model import RemovedCave
from nonebot.params import Depends
from .config import config
from sqlalchemy.exc import NoResultFound
from datetime import datetime, timedelta
from ...decoder import decode_cave

@cave.assign("remove.cave_id")
async def _(
    cave_id: int,
    session: async_scoped_session,
    is_superuser: bool = is_superuser(),
    user_id: str = get_user_id()
) -> None:
    try:
        cave_data = await session.get_one(
            CaveData,
            {"id": cave_id}
        )
    except NoResultFound:
        await lang.reply("remove.no_result", user_id)
        await cave.finish()
    if not (cave_data.author == user_id or is_superuser):
        await lang.reply("remove.no_permission", user_id)
        await cave.finish()
    if not cave_data.public:
        await lang.reply("remove.private", user_id, cave_id)
        await cave.finish()
    cave_data.public = False
    session.add(RemovedCave(
        id=cave_data.id,
        expiration_time=datetime.now() + timedelta(days=config.cave_restore_date),
        superuser=is_superuser
    ))
    post_time = cave_data.time.strftime("%Y-%m-%dT%H:%M:%S")
    await (await decode_cave(cave_data, session, user_id)).send()
    await session.commit()
    await lang.finish(
        "remove.success",
        user_id,
        cave_id,
        post_time,
        config.cave_restore_date,
        cave_id
    )
    

    