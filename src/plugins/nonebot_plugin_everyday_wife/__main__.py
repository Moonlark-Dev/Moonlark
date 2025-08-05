#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
import random

from nonebot import on_command
from nonebot_plugin_alconna import UniMessage

from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import Model, get_session, async_scoped_session
from sqlalchemy import String, select
from datetime import date
from sqlalchemy.orm import mapped_column, Mapped
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v12 import Bot as OneBotV12Bot
from nonebot.adapters.qq import Bot as QQBot
from typing import cast, Optional, NoReturn
from nonebot.matcher import Matcher
from nonebot.adapters import Event, Bot, Message
from nonebot.params import CommandArg
from nonebot_plugin_session import SessionId, SessionIdType
from nonebot_plugin_larkutils import get_user_id, get_group_id

lang = LangHelper()

class WifeData(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[str] = mapped_column(String(128))
    wife_id: Mapped[str] = mapped_column(String(128))
    queried: Mapped[bool] = mapped_column(default=False)
    generate_date: Mapped[date]

async def marry(couple: tuple[str, str], group_id: str) -> None:
    today = date.today()
    async with get_session() as session:
        await session.merge(WifeData(
            group_id=group_id,
            user_id=couple[0],
            wife_id=couple[1],
            generate_date=today,
            queried=False
        ))
        await session.merge(WifeData(
            group_id=group_id,
            user_id=couple[1],
            wife_id=couple[0],
            generate_date=today,
            queried=False
        ))

async def init_group(members: list[str], group_id: str) -> None:
    unmatched_members = []
    today = date.today()
    async with get_session() as session:
        for member in members:
            user_id = str(member)
            result = cast(Optional[WifeData], await session.scalar(select(WifeData).where(
                WifeData.group_id == group_id,
                WifeData.user_id == user_id
            )))
            if result is None or result.generate_date != today:
                unmatched_members.append(user_id)
    c = len(unmatched_members) // 2
    for i in range(c):
        couple = (
            unmatched_members.pop(random.randint(0, len(unmatched_members) - 1)),
            unmatched_members.pop(random.randint(0, len(unmatched_members) - 1)),
        )
        await marry(couple, group_id)

async def init_onebot_v11_group(bot: OneBotV11Bot, group_id: str) -> None:
    members = await bot.get_group_member_list(group_id=int(group_id))
    await init_group([user["user_id"] for user in members], group_id)


async def init_onebot_v12_group(bot: OneBotV12Bot, group_id: str) -> None:
    members = await bot.get_group_member_list(group_id=group_id)
    await init_group([user["user_id"] for user in members], group_id)

async def init_qq_group(bot: QQBot, group_id: str) -> None:
    members = await bot.post_group_members(group_id=group_id)
    await init_group([user.member_openid for user in members.members], group_id)

from nonebot_plugin_userinfo import get_user_info

async def divorce(group_id: str, session: async_scoped_session, platform_user_id: str) -> None:
    query = cast(Optional[WifeData], await session.scalar(select(WifeData).where(
        WifeData.user_id == platform_user_id,
        WifeData.group_id == group_id
    )))
    if query:
        result = await session.scalar(select(WifeData).where(
            WifeData.user_id == query.wife_id,
            WifeData.group_id == group_id
        ))
        if result:
            await session.delete(result)
        await session.delete(query)
    await session.commit()

def get_at_argument(message: Message) -> Optional[str]:
    for seg in message:
        if seg.type == "at":
            return seg.data["user_id"]
    return None

@on_command("wife", aliases={"today-wife", "waifu"}).handle()
async def _(
        matcher: Matcher,
        event: Event,
        session: async_scoped_session,
        bot: Bot,
        user_id: str = get_user_id(),
        group_id: str = SessionId(
            SessionIdType.GROUP,
            include_bot_type=False,
            include_bot_id=False,
            include_platform=False
        ),
        arg_message: Message = CommandArg()
) -> None:
    argv = arg_message.extract_plain_text().strip().lower()
    if isinstance(bot, OneBotV11Bot):
        await init_onebot_v11_group(bot, group_id)
    elif isinstance(bot, OneBotV12Bot):
        await init_onebot_v12_group(bot, group_id)
    elif isinstance(bot, QQBot):
        await init_qq_group(bot, group_id)
    platform_user_id = event.get_user_id()
    if argv == "divorce":
        await divorce(group_id, session, platform_user_id)
        await lang.finish("divorce", user_id, at_sender=True, reply_message=True)
    elif argv.startswith("force-marry"):
        target = get_at_argument(arg_message)
        if target is None:
            await lang.finish("no_target", user_id, at_sender=True, reply_message=True)
        await divorce(group_id, session, platform_user_id)
        await divorce(group_id, session, platform_user_id)
        await marry((platform_user_id, target), group_id)
        await lang.finish("force_success", user_id, at_sender=True, reply_message=True)

    query = cast(Optional[WifeData], await session.scalar(select(WifeData).where(
        WifeData.user_id == platform_user_id,
        WifeData.group_id == group_id,
        WifeData.generate_date == date.today()
    )))
    if query is None:
        await lang.finish("unmatched", user_id, at_sender=True)
    user_info = await get_user_info(bot, event, query.wife_id)
    message = UniMessage().text(text=await lang.text("matched", user_id)).at(user_id=query.wife_id)
    if user_info.user_avatar:
        message = message.image(url=user_info.user_avatar.get_url())
    if query.queried:
        message = message.text(text=await lang.text("queried", user_id))
    query.queried = True
    await session.commit()
    await matcher.finish(await message.export(), reply_message=True)








