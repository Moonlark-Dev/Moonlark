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
from datetime import datetime
from typing import Literal

from nonebot_plugin_alconna import UniMessage, Alconna, on_alconna, Args, Subcommand
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template, generate_render_keys
from nonebot_plugin_orm import async_scoped_session

from .models import BacReminderSubscription
from .utils import get_card_pool_data, get_activities, get_total_assault_data, SERVER_NAME_KEY

matcher = on_alconna(Alconna("ba-calendar", Args["server", Literal["in", "jp", "cn"], "cn"]), aliases={"bac"})
remind_matcher = on_alconna(
    Alconna(
        "bac-remind",
        Subcommand("on"),
        Subcommand("off"),
        Subcommand("server", Args["server_name", Literal["cn", "in", "jp"]]),
    ),
    block=True
)
lang = LangHelper()


@matcher.handle()
async def _(server: Literal["in", "jp", "cn"], user_id: str = get_user_id()) -> None:
    server_id = {"in": 17, "jp": 15, "cn": 16}[server]
    total_assault_data = await get_total_assault_data(server_id)
    await UniMessage().image(
        raw=await render_template(
            "ba_calendar.html.jinja",
            await lang.text("title", user_id),
            user_id,
            {
                "total_assault": total_assault_data,
                "card_pool": (await get_card_pool_data(server_id))["data"][::-1],
                "activities": await get_activities(server_id, [i["id"] for i in total_assault_data]),
                "current_time": datetime.now().timestamp(),
                
                "server_id": server_id,
                "len": len,
                "round": round,
            },
            await generate_render_keys(
                lang,
                user_id,
                [
                    f"template.{k}"
                    for k in [
                        "pool_title",
                        "coming_pool",
                        "current_up",
                        "activity_title",
                        "ongoing",
                        "day",
                        "a_remain",
                        "coming_activity",
                        "a_coming_remain",
                        "server_cn",
                        "server_jp",
                        "server_in",
                        "up_after",
                        "up_remain",
                        "total_assault",
                        "total_assault_ongoing",
                        "total_assault_soon",
                    ]
                ],
            ),
        )
    ).send()
    await matcher.finish()


@remind_matcher.assign("$main")
async def show_remind_status(
    event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id()
) -> None:
    """显示当前群的提醒状态"""
    if not isinstance(event, GroupMessageEvent):
        await lang.finish("reminder.command.group_only", user_id)
    
    group_id = str(event.group_id)
    subscription = await session.get(BacReminderSubscription, {"group_id": group_id})
    
    if subscription and subscription.enabled:
        status = await lang.text("reminder.command.enabled", user_id)
    else:
        status = await lang.text("reminder.command.disabled", user_id)
    
    server = subscription.server if subscription else "cn"
    server_text = await lang.text(f"reminder.{SERVER_NAME_KEY[server]}", user_id)
    
    await lang.finish("reminder.command.status", user_id, status, server_text)


@remind_matcher.assign("on")
async def enable_remind(
    event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id()
) -> None:
    """开启提醒"""
    if not isinstance(event, GroupMessageEvent):
        await lang.finish("reminder.command.group_only", user_id)
    
    group_id = str(event.group_id)
    subscription = await session.get(BacReminderSubscription, {"group_id": group_id})
    
    if subscription:
        subscription.enabled = True
    else:
        subscription = BacReminderSubscription(group_id=group_id, enabled=True, server="cn")
        session.add(subscription)
    
    await session.commit()
    await lang.finish("reminder.command.on_success", user_id)


@remind_matcher.assign("off")
async def disable_remind(
    event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id()
) -> None:
    """关闭提醒"""
    if not isinstance(event, GroupMessageEvent):
        await lang.finish("reminder.command.group_only", user_id)
    
    group_id = str(event.group_id)
    subscription = await session.get(BacReminderSubscription, {"group_id": group_id})
    
    if subscription:
        subscription.enabled = False
        await session.commit()
    
    await lang.finish("reminder.command.off_success", user_id)


@remind_matcher.assign("server")
async def set_server(
    event: GroupMessageEvent,
    server_name: Literal["cn", "in", "jp"],
    session: async_scoped_session,
    user_id: str = get_user_id()
) -> None:
    """设置服务器"""
    if not isinstance(event, GroupMessageEvent):
        await lang.finish("reminder.command.group_only", user_id)
    
    group_id = str(event.group_id)
    subscription = await session.get(BacReminderSubscription, {"group_id": group_id})
    
    if subscription:
        subscription.server = server_name
    else:
        subscription = BacReminderSubscription(group_id=group_id, enabled=True, server=server_name)
        session.add(subscription)
    
    await session.commit()
    server_text = await lang.text(f"reminder.{SERVER_NAME_KEY[server_name]}", user_id)
    await lang.finish("reminder.command.server_success", user_id, server_text)
