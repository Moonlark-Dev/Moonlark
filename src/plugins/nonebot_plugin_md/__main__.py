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

from nonebot import on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.adapters.qq import Bot as QQBot
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.superuser import is_superuser

lang = LangHelper()

md_cmd = on_command("md", permission=is_superuser)


@md_cmd.handle()
async def _handle_md(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    message: Message = CommandArg(),
) -> None:
    """将参数中的 Markdown 原样发送到当前会话，用于测试 QQ 官方机器人的 Markdown 渲染效果。"""
    await _process_md(md_cmd, bot, event, user_id, message.extract_plain_text().strip())


async def _process_md(matcher: Matcher, bot: Bot, event: Event, user_id: str, content: str) -> None:
    """/md 命令核心逻辑：仅支持 QQ 官方机器人，其余平台与空参数直接提示。"""
    if not isinstance(bot, QQBot):
        await lang.finish("unsupported_platform", user_id)
    if not content.strip():
        await lang.finish("empty", user_id)
    await UniMessage().style(content, "markdown").send(target=event, bot=bot)
    await matcher.finish()
