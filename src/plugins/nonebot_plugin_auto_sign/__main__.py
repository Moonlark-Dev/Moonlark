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
from typing import Any

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_bag.utils.reduce import ItemNotEnough, remove_item_from_bag
from nonebot_plugin_email.utils.send import send_email
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_orm import get_session
from nonebot_plugin_sign import (
    AUTO_SIGN_TICKET_ID,
    get_auto_sign_ticket_count,
    is_user_signed,
    perform_sign,
)
from nonebot_plugin_sign.models import SignData
from sqlalchemy import select

from .lang import lang


async def get_auto_enabled_user_ids() -> list[str]:
    """获取所有开启自动签到的用户"""
    async with get_session() as session:
        result = await session.scalars(select(SignData.user_id).where(SignData.auto_enabled.is_(True)))
        return list(result.all())


async def is_auto_sign_allowed(user_id: str) -> bool:
    """检查用户是否满足自动签到条件（开启自动签到、未超出使用限制且持有自动签到券）"""
    async with get_session() as session:
        data = await session.get(SignData, {"user_id": user_id})
    if data is None or not data.auto_enabled:
        return False
    # 使用限制：auto_limit <= 0 为不限制，否则自上次重置后使用的数量不能达到上限
    if data.auto_limit > 0 and data.auto_used >= data.auto_limit:
        return False
    return await get_auto_sign_ticket_count(user_id) >= 1


async def send_result_email(user_id: str, result: dict[str, Any]) -> None:
    """将自动签到结果通过邮件推送"""
    lines = [
        await lang.text("email.header", user_id),
        await lang.text("email.sign_days", user_id, result["sign_days"]),
        await lang.text("email.exp", user_id, result["exp"]["add"], result["exp"]["now"]),
        await lang.text("email.vim", user_id, result["vim"]["add"], result["vim"]["now"]),
        await lang.text("email.fav", user_id, result["fav"]["add"]),
    ]
    if result["ticket_gained"]:
        lines.append(await lang.text("email.ticket_gained", user_id, result["sign_days"]))
    lines.append(await lang.text("email.consumed", user_id))
    await send_email([user_id], await lang.text("email.subject", user_id), "\n".join(lines))


async def auto_sign(user_id: str) -> bool:
    """为用户执行一次自动签到，返回是否执行

    条件：持有自动签到券、允许自动签到、自上次重置后使用的自动签到券数量未达上限。
    """
    if await is_user_signed(user_id):
        return False
    if not await is_auto_sign_allowed(user_id):
        return False

    # 消耗一张自动签到券
    await remove_item_from_bag(user_id, get_location_by_id(AUTO_SIGN_TICKET_ID), 1)

    # 签到并按正常流程发放奖励（不发送签到面板）
    result = await perform_sign(user_id, auto=True)
    if result is None:
        logger.warning(f"Auto sign skipped for {user_id}: already signed after ticket consumed")
        return False

    # 推送签到结果邮件
    await send_result_email(user_id, result)
    return True


async def run_auto_sign() -> None:
    """遍历开启自动签到的用户并尝试自动签到"""
    logger.info("Auto sign started")
    signed_count = skipped_count = failed_count = 0
    for user_id in await get_auto_enabled_user_ids():
        try:
            if await auto_sign(user_id):
                signed_count += 1
            else:
                skipped_count += 1
        except ItemNotEnough as e:
            skipped_count += 1
            logger.warning(f"Auto sign skipped for {e.user_id}: {e}")
        except Exception as e:
            failed_count += 1
            logger.exception(f"Auto sign failed for {user_id}: {e}")
    logger.info(f"Auto sign finished: {signed_count} signed, {skipped_count} skipped, {failed_count} failed")


@scheduler.scheduled_job("cron", hour=23, minute=55, id="auto_sign_daily", misfire_grace_time=3600)
async def _() -> None:
    await run_auto_sign()
