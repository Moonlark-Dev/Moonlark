from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.command import get_command_prefix

from ..__main__ import lang, quick_math
from ..utils.ranking import get_weekly_user_list


async def get_menu_markdown(user_id: str, append_commands: bool) -> str:
    """生成 /qm 主界面 markdown：玩法介绍 + 周积分排行榜 + 模式介绍。

    :param append_commands: 非 QQ 适配器（无按钮）时在末尾追加全部模式的指令说明。
    """
    intro = await lang.text("menu.intro", user_id)
    weekly, my_points = await get_weekly_user_list(user_id)
    weekly_lines = [await lang.text("menu.weekly", user_id)]
    if weekly:
        for index, data in enumerate(weekly, start=1):
            user = await get_user(data.user_id)
            nickname = user.get_nickname() if user.has_nickname() else await lang.text("rank.default_nickname", user_id)
            weekly_lines.append(await lang.text("menu.weekly_item", user_id, index, nickname, data.points))
    else:
        weekly_lines.append(await lang.text("menu.weekly_empty", user_id))
    if my_points > 0:
        weekly_lines.append(await lang.text("menu.weekly_me", user_id, my_points))
    parts = [intro, "\n".join(weekly_lines), await lang.text("menu.modes", user_id)]
    if append_commands:
        parts.append(await lang.text("menu.commands", user_id))
    return "\n\n".join(parts)


@quick_math.assign("$main")
async def menu_handler(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    if isinstance(bot, QQBot):
        prefix = get_command_prefix()
        await (
            UniMessage()
            .style(await get_menu_markdown(user_id, append_commands=False), "markdown")
            .keyboard(
                Button("enter", await lang.text("button.start", user_id), text=f"{prefix}qm start"),
                Button("enter", await lang.text("button.zen", user_id), text=f"{prefix}qm zen 5"),
                Button("enter", await lang.text("button.rank", user_id), text=f"{prefix}qm rank"),
                Button("enter", await lang.text("button.points", user_id), text=f"{prefix}qm points"),
                Button("enter", await lang.text("button.pvp-create", user_id), text=f"{prefix}qm pvp create"),
            )
            .send(target=event, bot=bot)
        )
        await quick_math.finish()
    else:
        image = await md_to_pic(await get_menu_markdown(user_id, append_commands=True))
        await quick_math.finish(UniMessage().image(raw=image))
