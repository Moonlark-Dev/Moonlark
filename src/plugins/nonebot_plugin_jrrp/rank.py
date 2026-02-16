from typing import AsyncGenerator, NoReturn
from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_larkuser.utils.user import get_registered_user_ids
from nonebot_plugin_orm import get_session
from .lang import lang
from nonebot_plugin_render import render_template
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_larkutils import get_user_id, get_group_id
from .__main__ import jrrp
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_chat.core.session import post_group_event


async def get_user_list() -> AsyncGenerator[tuple[str, int], None]:
    session = get_session()
    for user in await get_registered_user_ids():
        yield user, await get_luck_value(user)
    await session.close()


async def get_rank(sender_id: str, reverse: bool = False) -> NoReturn:
    data = sorted([data async for data in get_user_list()], key=lambda x: x[1], reverse=not reverse)
    templates = {}
    for i in range(min(3, len(data))):
        user_id = data[i][0]
        user = await get_user(user_id)
        templates[f"luckiest_{i + 1}"] = {
            "user_id": user_id,
            "value": data[i][1],
            "avatar": user.get_base64_avatar(),
            "nickname": user.get_nickname(),
        }
    i = 0
    sender_luck = 0
    for user_id, value in data:
        i += 1
        if user_id != sender_id:
            continue
        user = await get_user(user_id)
        sender_luck = value
        templates["user"] = {
            "index": i,
            "nickname": user.get_nickname(),
            "data": value,
            "info": await lang.text("forward", user_id, round((len(data) - i) / len(data) * 100, 1)),
        }
        break
    else:
        templates["user"] = None

    try:
        # Calculate Lucky Star and Unlucky One
        sorted_data = sorted(data, key=lambda x: x[1], reverse=True)
        lucky_star_id, lucky_star_value = sorted_data[0]
        unlucky_one_id, unlucky_one_value = sorted_data[-1]

        lucky_star_user = await get_user(lucky_star_id)
        unlucky_one_user = await get_user(unlucky_one_id)

        lucky_star_nickname = lucky_star_user.get_nickname()
        unlucky_one_nickname = unlucky_one_user.get_nickname()

        event_prompt = await lang.text(
            "group_event_prompt",
            sender_id,
            sender_luck,
            lucky_star_nickname,
            lucky_star_value,
            unlucky_one_nickname,
            unlucky_one_value,
        )
        await post_group_event(get_group_id(), event_prompt, "probability")
    except Exception as e:
        logger.exception(e)

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
