from typing import AsyncGenerator, NoReturn
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_larkuser.utils.user import get_registered_user_ids
from nonebot_plugin_orm import get_session
from .lang import lang
from nonebot_plugin_render import render_template
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_larkutils import get_user_id
from .__main__ import jrrp
from nonebot_plugin_larkuser import get_user


async def get_user_list() -> AsyncGenerator[tuple[str, int], None]:
    session = get_session()
    for user in await get_registered_user_ids():
        yield user, get_luck_value(user)
    await session.close()


async def get_rank(sender_id: str, reverse: bool = False) -> NoReturn:
    data = sorted([data async for data in get_user_list()], key=lambda x: x[1], reverse=not reverse)
    templates = {}
    for i in range(3):
        user_id = data[i][0]
        user = await get_user(user_id)
        templates[f"luckiest_{i + 1}"] = {
            "user_id": user_id,
            "value": data[i][1],
            "avatar": user.get_base64_avatar(),
            "nickname": user.get_nickname(),
        }
    i = 0
    for user_id, value in data:
        i += 1
        if user_id != sender_id:
            continue
        user = await get_user(user_id)
        templates["user"] = {
            "index": i,
            "nickname": user.get_nickname(),
            "data": value,
            "info": await lang.text("forward", user_id, round((len(data) - i) / len(data) * 100, 1)),
        }
        break
    else:
        templates["user"] = None
    image = await render_template(
        f"jrrp_rank{'_reverse' if reverse else ''}.html.jinja",
        await lang.text("rank.title", sender_id),
        sender_id,
        templates,
        dict(
            [(key, await lang.text(f"template.{key}", user_id)) for key in ["reverse_title", "unregistered", "title"]]
        ),
    )
    await jrrp.finish(UniMessage().image(raw=image))


@jrrp.assign("rank")
async def _(sender_id: str = get_user_id()) -> None:
    await get_rank(sender_id)


@jrrp.assign("rank-r")
async def _(sender_id: str = get_user_id()) -> None:
    await get_rank(sender_id, True)
