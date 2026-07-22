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
from nonebot.permission import SUPERUSER
from nonebot.log import logger
from nonebot_plugin_alconna import Alconna, Args, MultiVar, on_alconna
from nonebot.adapters.qq import Bot as QQBot, GroupMessageCreateEvent

send_cmd = on_alconna(
    Alconna("send", Args["text?", MultiVar(str)]),
    permission=SUPERUSER,
    use_cmd_start=True,
    block=True,
)


@send_cmd.handle()
async def handle_send(bot: Bot, event: Event, text: tuple[str, ...] | None = None) -> None:
    # 仅支持 QQ 适配器
    if not isinstance(bot, QQBot):
        await send_cmd.finish("该命令仅支持 QQ 适配器")

    # 仅支持群聊（GroupAtMessageCreateEvent 也会匹配到 GroupMessageCreateEvent）
    if not isinstance(event, GroupMessageCreateEvent):
        await send_cmd.finish("该命令仅支持群聊使用")

    if not text:
        await send_cmd.finish("请输入要发送的内容")

    # 将 text 原封不动地传给群聊发送接口
    content = " ".join(text)

    try:
        await bot.send_to_group(group_openid=event.group_openid, message=content)
        logger.info(f"调试发送成功: group={event.group_openid}, text={content!r}")
        await send_cmd.finish("发送成功喵～")
    except Exception as e:
        logger.error(f"调试发送失败: {e}")
        await send_cmd.finish(f"发送失败: {e}")
