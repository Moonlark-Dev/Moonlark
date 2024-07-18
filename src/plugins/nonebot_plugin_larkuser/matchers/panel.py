from nonebot import on_command
from nonebot.matcher import Matcher
from nonebot_plugin_alconna.uniseg import UniMessage
from src.plugins.nonebot_plugin_render.render import render_template
from src.plugins.nonebot_plugin_larkutils import get_user_id

from ..lang import lang
from ..utils.matcher import patch_matcher
from ..utils.user import get_user


@patch_matcher(on_command("panel")).handle()
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    level = user.get_level()
    level_progress = int((user.experience - (level - 1) ** 3) / (level**3 - (level - 1) ** 3) * 100)
    message = UniMessage().image(
        raw=await render_template(
            "panel.html.jinja",
            await lang.text("panel.title", user_id),
            user_id,
            {
                "nickname": user.get_nickname(),
                "user_id": await lang.text("panel.uid", user_id, user_id),
                "avatar": user.get_base64_avatar(),
                "level": await lang.text(
                    "panel.level",
                    user_id,
                    level,
                    user.experience - (level - 1) ** 3,
                    level**3,
                ),
                "level_progress": f"{level_progress}%",
                "vimcoin": await lang.text("panel.vimcoin", user_id, round(user.get_vimcoin(), 3)),
                "fav": await lang.text("panel.fav", user_id, round(user.get_fav(), 3)),
                "hp": await lang.text("panel.hp", user_id, round(user.get_health(), 3)),
                "hp_progress": f"{int(user.get_health())}%",
            },
        ),
        name="image.png",
    )
    await matcher.finish(await message.export(), at_sender=True)
