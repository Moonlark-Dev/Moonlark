#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq.bot import Bot as QQBot
from nonebot.adapters.qq.event import C2CMessageCreateEvent
from nonebot_plugin_alconna import Alconna, Button, UniMessage, on_alconna
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkutils import get_user_id

from .lang import lang
from .store import load_announcement
from .types import UpdateAnnouncement
from .utils import mark_update_read

updates = on_alconna(Alconna("updates"))


def build_markdown(announcement: UpdateAnnouncement, at_user: str = "") -> str:
    """将更新公告渲染为 markdown 文本"""
    at = f"{at_user}\n\n" if at_user else ""
    return f"{at}## {announcement.title}\n\n{announcement.content}"


@updates.handle()
async def _(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    announcement = await load_announcement()
    if announcement is None:
        await lang.finish("none", user_id)
    await mark_update_read(user_id)
    if isinstance(bot, QQBot):
        # QQ 官方适配器：发送 markdown 正文，公告自带按钮作为键盘按钮下发（群聊中可推送查看）
        at_user = "" if isinstance(event, C2CMessageCreateEvent) else f'<qqbot-at-user id="{event.get_user_id()}" />'
        buttons = [Button("enter", button.label, text=button.text) for button in announcement.buttons]
        message = UniMessage().style(build_markdown(announcement, at_user), "markdown")
        if buttons:
            message = message.keyboard(*buttons)
        await message.send(target=event, bot=bot)
        await updates.finish()
    # 其他适配器：正文渲染为图片发送，不显示按钮
    image = await md_to_pic(build_markdown(announcement))
    await updates.finish(UniMessage().image(raw=image))
