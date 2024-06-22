import base64
from pathlib import Path

from nonebot import on_command
from nonebot.matcher import Matcher
from nonebot_plugin_alconna.uniseg import UniMessage

from ..nonebot_plugin_render.render import render_template

from ..nonebot_plugin_larkutils import get_user_id
from .lang import lang
from .matcher import patch_matcher
from .utils.level import get_level_by_experience
from .utils.user import get_user


@patch_matcher(on_command("panel")).handle()
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    await matcher.finish(
        await UniMessage()
        .image(
            raw=await render_template(
                "panel.html.jinja",
                await lang.text("panel.title", user_id),
                user_id,
                {
                    "nickname": user.nickname,
                    "user_id": await lang.text("panel.uid", user_id, user_id),
                    "avatar": base64.b64encode(user.avatar).decode() if user.avatar is not None else None,
                    "level": await lang.text(
                        "panel.level",
                        user_id,
                        (level := get_level_by_experience(user.experience)),
                        user.experience - (level - 1) ** 3,
                        (level) ** 3,
                    ),
                    "level_progress": f"{int((user.experience - (level - 1) ** 3) / ((level) ** 3 - (level - 1) ** 3) * 100)}%",
                    "vimcoin": await lang.text("panel.vimcoin", user_id, round(user.vimcoin, 3)),
                    "fav": await lang.text("panel.fav", user_id, round(user.favorability, 3)),
                    "hp": await lang.text("panel.hp", user_id, round(user.health, 3)),
                    "hp_progress": f"{int(user.health)}%",
                },
            ),
            name="image.png",
        )
        .export(),
        at_sender=True,
    )
