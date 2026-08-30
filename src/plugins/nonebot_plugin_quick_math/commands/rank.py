from typing import Literal, Optional

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_larkutils import get_user_id

from ..__main__ import lang, quick_math
from ..config import config
from ..models import QuickMathUser
from ..utils.ranking import get_user_list


async def generate_rank_markdown(ranked_data: list[dict], title: str, user_id: str, limit: int = 7) -> str:
    """将排行数据渲染为 QQ 官方机器人可用的 markdown 文本。"""
    lines = [f"**{title}**", ""]
    me: Optional[dict] = None
    for index, data in enumerate(ranked_data, start=1):
        if data["user_id"] == user_id:
            user = await get_user(data["user_id"])
            me = {
                "index": index,
                "user_id": data["user_id"],
                "data": data["data"],
                "nickname": (
                    user.get_nickname() if user.has_nickname() else await lang.text("rank.default_nickname", user_id)
                ),
            }
            break
    for index, data in enumerate(ranked_data[:limit], start=1):
        user = await get_user(data["user_id"])
        nickname = user.get_nickname() if user.has_nickname() else await lang.text("rank.default_nickname", user_id)
        lines.extend(
            [
                await lang.text("rank.md_item", user_id, index, nickname, data["data"]),
                await lang.text("rank.md_info", user_id, data["user_id"]),
            ],
        )
    if me is not None:
        lines.append(await lang.text("rank.md_me", user_id, me["index"]))
        lines.extend(
            [
                await lang.text("rank.md_item", user_id, me["index"], me["nickname"], me["data"]),
                await lang.text("rank.md_info", user_id, me["user_id"]),
            ],
        )
    return "\n".join(lines)


@quick_math.assign("rank")
async def handle(bot: Bot, rank_type: Literal["max", "total"] = "max", user_id: str = get_user_id()) -> None:
    order_by = QuickMathUser.max_point if rank_type == "max" else QuickMathUser.experience
    data = [
        {"user_id": user.user_id, "data": user.max_point if rank_type == "max" else user.experience, "info": None}
        async for user in get_user_list(order_by)
    ]
    title = await lang.text(f"rank.title-{1 if rank_type == 'max' else 2}", user_id)
    if isinstance(bot, QQBot):
        await (
            UniMessage()
            .style(await generate_rank_markdown(data, title, user_id), "markdown")
            .keyboard(
                Button(
                    "enter",
                    await lang.text("button.rank-record", user_id),
                    text=f"{config.command_start[0]}qm rank",
                ),
                Button(
                    "enter",
                    await lang.text("button.rank-total", user_id),
                    text=f"{config.command_start[0]}qm rank -t",
                ),
            )
            .send()
        )
        await quick_math.finish()
    else:
        image = await generate_image(data, user_id, title)
        await quick_math.finish(UniMessage().image(raw=image))


@quick_math.assign("total")
async def _(bot: Bot, user_id: str = get_user_id()) -> None:
    await handle(bot, "total", user_id)
