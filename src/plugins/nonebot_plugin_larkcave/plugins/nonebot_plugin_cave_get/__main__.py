from ...decoder import decode_cave
from ...model import CaveData
from ...__main__ import cave
from ....nonebot_plugin_larkutils import get_user_id, is_superuser
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound
from ...lang import lang


@cave.assign("get.cave_id")
async def _(
    session: async_scoped_session,
    cave_id: int,
    user_id: str = get_user_id(),
    is_superuser: bool = is_superuser()
) -> None:
    try:
        cave_data = await session.get_one(
            CaveData,
            {"id": cave_id}
        )
        content = await decode_cave(cave_data, session, user_id)
    except NoResultFound:
        await lang.finish("get.not_found", user_id, cave_id)
        await cave.finish()
    if (not cave_data.public) and not is_superuser:
        await lang.finish("get.no_premission", user_id)
        await cave.finish()
    if not ((cave_data.author == cave_data.author) or is_superuser):
        await lang.finish("get.no_premission", user_id)
        await cave.finish()
    await cave.finish(content)



