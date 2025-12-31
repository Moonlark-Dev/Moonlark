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
import traceback
from datetime import datetime
from typing import Literal

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage, Target
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from sqlalchemy import select, and_

from .models import BacReminderSubscription, BacReminderSent
from .utils import get_total_assault_data, get_image, SERVER_ID_MAP, SERVER_NAME_KEY

lang = LangHelper()

# 提醒时间窗口（秒）：70 分钟，给定时任务 10 分钟缓冲
REMINDER_WINDOW = 4200


async def check_and_mark_reminder(activity_id: int, reminder_type: str, server: str) -> bool:
    """检查提醒是否已发送，如未发送则标记并返回 True"""
    async with get_session() as session:
        result = await session.execute(
            select(BacReminderSent).where(
                and_(
                    BacReminderSent.activity_id == activity_id,
                    BacReminderSent.reminder_type == reminder_type,
                    BacReminderSent.server == server
                )
            )
        )
        if result.scalar_one_or_none() is not None:
            return False
        
        session.add(BacReminderSent(
            activity_id=activity_id,
            reminder_type=reminder_type,
            server=server
        ))
        await session.commit()
        return True


async def get_subscribed_groups(server: str) -> list[str]:
    """获取订阅了指定服务器的群聊列表"""
    async with get_session() as session:
        result = await session.execute(
            select(BacReminderSubscription.group_id).where(
                and_(
                    BacReminderSubscription.enabled == True,
                    BacReminderSubscription.server == server
                )
            )
        )
        return [row[0] for row in result.all()]


async def send_to_group(group_id: str, message: UniMessage) -> bool:
    """向指定群聊发送消息，返回是否成功"""
    for bot in get_bots().values():
        if not isinstance(bot, V11Bot):
            continue
        try:
            groups = await bot.get_group_list()
            if any(str(g["group_id"]) == group_id for g in groups):
                await message.send(
                    target=Target(group_id, self_id=bot.self_id, adapter=bot.adapter.get_name()),
                    bot=bot
                )
                return True
        except Exception:
            logger.warning(f"向群 {group_id} 发送消息失败: {traceback.format_exc()}")
    return False


async def build_reminder_message(
    activity: dict, 
    reminder_type: Literal["start", "end"], 
    server: str,
) -> UniMessage:
    """构建提醒消息"""
    user_id = "mlsid::--lang=zh_hans"
    
    status_key = f"reminder.status_{reminder_type}"
    server_key = f"reminder.{SERVER_NAME_KEY[server]}"
    
    text_content = await lang.text(
        "reminder.message",
        user_id,
        activity["title"],
        await lang.text(status_key, user_id),
        await lang.text(server_key, user_id)
    )
    
    message = UniMessage().text(text_content)
    
    # 尝试获取并添加图片
    if activity.get("picture"):
        try:
            image_data = await get_image(activity["picture"])
            message = message.image(url=image_data)
        except Exception as e:
            logger.warning(f"获取活动图片失败: {e}")
    
    return message


def get_reminder_type(activity: dict) -> Literal["start", "end"] | None:
    """判断活动需要发送哪种提醒，返回 None 表示不需要提醒"""
    current_time = datetime.now().timestamp()
    begin_at = activity.get("begin_at", 0)
    end_at = activity.get("end_at", 0)
    
    # 优先检查结束提醒（活动已开始）
    if current_time >= begin_at:
        if 0 < end_at - current_time <= REMINDER_WINDOW:
            return "end"
    # 检查开始提醒
    elif 0 < begin_at - current_time <= REMINDER_WINDOW:
        return "start"
    
    return None


async def process_server_reminders(server: str) -> None:
    """处理指定服务器的所有提醒"""
    server_id = SERVER_ID_MAP[server]
    groups = await get_subscribed_groups(server)
    
    if not groups:
        return
    
    try:
        activities = await get_total_assault_data(server_id, fetch_images=False)
    except Exception as e:
        logger.error(f"获取服务器 {server} 的总力战数据失败: {e}")
        return
    
    for activity in activities:
        activity_id = activity.get("id")
        if not activity_id:
            continue
        
        reminder_type = get_reminder_type(activity)
        if not reminder_type:
            continue
        
        if not await check_and_mark_reminder(activity_id, reminder_type, server):
            continue
        
        logger.info(f"发送 {server} 服务器总力战提醒: {activity['title']} ({reminder_type})")
        
        message = await build_reminder_message(activity, reminder_type, server)
        
        for group_id in groups:
            await send_to_group(group_id, message)
            await asyncio.sleep(1)


@scheduler.scheduled_job("cron", minute="*/10", id="bac_reminder_check")
async def check_and_send_reminders() -> None:
    """定时检查并发送提醒"""
    logger.debug("检查蔚蓝档案总力战提醒...")
    
    for server in SERVER_ID_MAP:
        try:
            await process_server_reminders(server)
        except Exception:
            logger.error(f"处理服务器 {server} 提醒时出错: {traceback.format_exc()}")