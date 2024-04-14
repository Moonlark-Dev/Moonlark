from nonebot_plugin_alconna import AlconnaMatch, Arparma, Match
from ...__main__ import cave
from ...lang import lang
from ...model import GroupData
from ....nonebot_plugin_larkutils import get_user_id, get_group_id, is_superuser
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound
from ...cool_down import is_group_cooled, is_user_cooled

async def set_cool_down(group_id: str, time: float, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        session.add(GroupData(
            group_id=group_id,
            cool_down_time=time
        ))
    else:
        data.cool_down_time = time
    await session.commit()


@cave.assign("cd")
async def _(
    session: async_scoped_session,
    alc_result: Arparma,
    time: Match[float] = AlconnaMatch("time"),
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    is_superuser: bool = is_superuser()
) -> None:
    if time.available:
        if is_superuser:
            await set_cool_down(group_id, time.result, session)
            await lang.finish("cd.set", user_id)
        else:
            await lang.finish("cd.no_permission", user_id)
    if alc_result.find("cd.user"):
        result = await is_user_cooled(user_id, session)
        await lang.finish(
            "cd.info_user",
            user_id,
            await lang.text(
                "cd.info_status_ok" if result[0] else "cd.info_status_cooling",
                user_id
            ),
            0 if result[0] else round(result[1] / 60, 3),
            at_sender=False
        )
    result = await is_group_cooled(group_id, session)
    await lang.finish(
        "cd.info",
        user_id,
        await lang.text(
            "cd.info_status_ok" if result[0] else "cd.info_status_cooling",
            user_id
        ),
        0 if result[0] else round(result[1] / 60, 3),
        at_sender=False
    )

