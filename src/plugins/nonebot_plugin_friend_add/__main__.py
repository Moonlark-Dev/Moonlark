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
import json

import aiofiles
from nonebot.adapters.onebot.v11.event import FriendAddNoticeEvent, FriendRequestEvent
from nonebot.adapters.onebot.v12.event import FriendIncreaseEvent
from nonebot.adapters.qq.event import FriendAddEvent
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.adapters.onebot.v11 import Bot as BotOB
from nonebot_plugin_localstore import get_data_file
from nonebot import on_type
from datetime import datetime
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkuser import get_user
from ..nonebot_plugin_larkutils import get_user_id
from .config import config

lang = LangHelper()
friend_add_qq = on_type(FriendAddEvent)
friend_request = on_type(FriendRequestEvent)
friend_add_ob = on_type(FriendAddNoticeEvent)
friend_add_ob12 = on_type(FriendIncreaseEvent)
data_file = get_data_file("nonebot_plugin_friend_add", "friends.json")


async def get_friends() -> dict[str, float]:
    try:
        async with aiofiles.open(data_file, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning(traceback.format_exc())
        return {}


async def write_friends_file(data: dict[str, float]) -> None:
    async with aiofiles.open(data_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data))


@friend_add_qq.handle()
async def _(bot: BotQQ, event: FriendAddEvent, user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    if user_id not in (friends := await get_friends()):
        await user.add_fav(config.friend_add_award_fav)
        friends[user_id] = datetime.now().timestamp()
        await write_friends_file(friends)
        await bot.send_to_c2c(event.openid, await lang.text("text.default", user_id))
    elif (datetime.now() - datetime.fromtimestamp(friends[user_id])).days < 1:
        pass
    elif user.has_nickname():
        await bot.send_to_c2c(event.openid, await lang.text("text.more_with_nickname", user_id, user.get_nickname()))
    else:
        await bot.send_to_c2c(event.openid, await lang.text("text.default", user_id))
    await friend_add_qq.finish()


@friend_request.handle()
async def _(bot: BotOB, event: FriendRequestEvent, user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    if user.get_fav() <= 0.05:
        await event.reject(bot)
    elif (
        user_id in (friends := await get_friends())
        and (datetime.now() - datetime.fromtimestamp(friends[user_id])).total_seconds() < 1800
    ):
        await event.reject(bot)
    else:
        await event.approve(bot)


@friend_add_ob12.handle()
@friend_add_ob.handle()
async def _(user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    if user_id not in (friends := await get_friends()):
        await user.add_fav(config.friend_add_award_fav)
        friends[user_id] = datetime.now().timestamp()
        await write_friends_file(friends)
        await lang.finish("text.default", user_id)
    elif user.has_nickname():
        await lang.finish("text.more_with_nickname", user_id, user.get_nickname())
    else:
        await lang.finish("text.default", user_id)
