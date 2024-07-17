from ..nonebot_plugin_cave_remove.models import RemovedCave
from ...lang import lang
from ...models import CaveData
from nonebot_plugin_orm import async_scoped_session
from ....nonebot_plugin_larkutils import get_user_id, is_user_superuser
from ...__main__ import cave
from sqlalchemy.exc import NoResultFound


@cave.assign("restore.cave_id")
async def _(
    session: async_scoped_session, cave_id: int, user_id: str = get_user_id(), is_user_superuser: bool
) -> None:
    try:
        data = await session.get_one(RemovedCave, {"id": cave_id})
        cave_data = await session.get_one(CaveData, {"id": cave_id})
    except NoResultFound:
        await lang.finish("restore.not_found", user_id, cave_id)
        await cave.finish()
    if not ((user_id == cave_data.author and not data.superuser) or is_superuser):
        await lang.finish("restore.no_permission", user_id)
        await cave.finish()
    await session.delete(data)
    await session.commit()
    cave_data.public = True
    await session.commit()
    await lang.finish("restore.success", user_id, cave_id)
