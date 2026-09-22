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

"""QQ 官方 Bot 群成员缓存的发现与周期性刷新。

群成员列表接口自身没有「推送」能力，而 Moonlark 又需要知道群里有谁，因此这里：

- 收到 QQ 群消息时登记该群，并在后台同步一次群信息与成员列表；
- 周期性任务按缓存有效期刷新所有已登记群的群信息与成员列表。
"""

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

from ..config import config
from .cache import ensure_group_known, sync_all_groups


def _is_qq_group_message(bot: Bot) -> bool:
    """规则：仅处理 QQ 官方 Bot 的群聊消息"""
    return isinstance(bot, QQBot)


group_sync_matcher = on_message(block=False, priority=9, rule=_is_qq_group_message)


@group_sync_matcher.handle()
async def _(bot: Bot, event: Event) -> None:
    if not isinstance(bot, QQBot) or not isinstance(event, GroupMessageCreateEvent):
        return
    if not config.qq_group_sync_enabled:
        return
    await ensure_group_known(bot, event.group_openid)


@scheduler.scheduled_job(
    "interval",
    seconds=config.qq_group_sync_interval,
    id="larkuser_qq_group_cache_sync",
    max_instances=1,
)
async def _sync_qq_group_cache() -> None:
    try:
        await sync_all_groups()
    except Exception as e:
        logger.exception(f"[larkuser] 刷新 QQ 群成员缓存失败: {e}")
