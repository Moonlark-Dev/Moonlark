#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

import asyncio
from datetime import datetime

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage, Target
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import TimeProgressSubscription
from .utils import get_year_progress_integer, generate_progress_bar

lang = LangHelper()


async def get_groups_to_notify(year: int, percentage: int) -> list[str]:
    """
    获取需要通知的群聊列表，并更新其发送记录

    Returns:
        需要通知的 group_id 列表
    """
    async with get_session() as session:
        result = await session.execute(select(TimeProgressSubscription).where(TimeProgressSubscription.enabled == True))
        subscriptions = result.scalars().all()

        to_notify = []
        for sub in subscriptions:
            # 检查是否需要发送（年份不同或百分比更大）
            if sub.last_sent_year != year or sub.last_sent_percentage < percentage:
                sub.last_sent_year = year
                sub.last_sent_percentage = percentage
                to_notify.append(sub.group_id)

        await session.commit()
        return to_notify


async def send_to_group(group_id: str, message: UniMessage) -> bool:
    """向指定群聊发送消息"""
    for bot in get_bots().values():
        if not isinstance(bot, V11Bot):
            continue
        try:
            groups = await bot.get_group_list()
            if any(str(g["group_id"]) == group_id for g in groups):
                await message.send(
                    target=Target(group_id, self_id=bot.self_id, adapter=bot.adapter.get_name()), bot=bot
                )
                return True
        except Exception as e:
            logger.warning(f"向群 {group_id} 发送年进度消息失败: {e}")
    return False


async def build_progress_message(year: int, percentage: int) -> UniMessage:
    """构建进度推送消息"""
    user_id = "mlsid::--lang=zh_hans"
    progress_bar = generate_progress_bar(percentage)
    text = await lang.text("sub.push_message", user_id, year, progress_bar, percentage)
    return UniMessage().text(text)


@scheduler.scheduled_job("cron", minute="0", id="time_progress_push")
async def check_and_push_progress() -> None:
    """每小时检查并推送年进度"""
    current_year = datetime.now().year
    current_percentage = get_year_progress_integer()

    if current_percentage <= 0 or current_percentage > 100:
        return

    # 获取需要通知的群聊（同时更新发送记录）
    groups_to_notify = await get_groups_to_notify(current_year, current_percentage)

    if not groups_to_notify:
        return

    logger.info(f"发送年进度推送: {current_year} 年 {current_percentage}%，共 {len(groups_to_notify)} 个群")

    message = await build_progress_message(current_year, current_percentage)

    for group_id in groups_to_notify:
        await send_to_group(group_id, message)
        await asyncio.sleep(1)
