from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import C2CMessageCreateEvent
from nonebot.matcher import Matcher
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_render.render import render_template
from nonebot_plugin_larkutils import create_image_markdown, get_user_id

from ..lang import lang
from ..utils.matcher import patch_matcher
from ..utils.user import get_user


async def get_user_info(matcher: Matcher, bot: Bot, event: Event, user_id: str) -> None:
    user = await get_user(user_id)
    level = user.get_level()
    level_progress = int((user.experience - (level - 1) ** 3) / (level**3 - (level - 1) ** 3) * 100)
    image = await render_template(
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
            "fav": await lang.text("panel.fav", user_id, user.get_display_fav(), await user.get_fav_level()),
            "hp": await lang.text("panel.hp", user_id, round(user.get_health(), 3)),
            "hp_progress": f"{int(user.get_health())}%",
        },
    )
    if isinstance(bot, QQBot):
        # QQ 官方的 at 只支持 markdown；图片消息（msg_type=7）不能携带 at，
        # 因此与 sign 一致，把图片上传到 QQ 素材库后用 markdown 内嵌。
        at_user = "" if isinstance(event, C2CMessageCreateEvent) else f'<qqbot-at-user id="{event.get_user_id()}" />'
        await (
            UniMessage()
            .style(f"{at_user}{await create_image_markdown(image, bot)}", "markdown")
            .send(target=event, bot=bot)
        )
        await matcher.finish()
        return
    await matcher.finish(await UniMessage().image(raw=image, name="image.png").export(), at_sender=True)


@patch_matcher(on_command("panel")).handle()
async def _(matcher: Matcher, bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    await get_user_info(matcher, bot, event, user_id)
