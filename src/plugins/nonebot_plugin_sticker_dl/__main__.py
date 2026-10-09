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

from typing import NoReturn, Optional

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot_plugin_alconna import Alconna, Image, UniMessage, image_fetch, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import Waiter, patch_matcher
from nonebot_plugin_larkutils import get_user_id

PROMPT_TIMEOUT = 5 * 60
"""单次等待表情包的秒数，超时后退出表情包下载模式。"""

active_users: set[str] = set()
"""当前处于表情包下载模式的用户主账号 ID。"""


def is_not_downloading(user_id: str = get_user_id()) -> bool:
    """已在表情包下载模式中的用户再次发送指令时，交给模式内的 prompt 处理（按非图片消息退出）。"""
    return user_id not in active_users


matcher = on_alconna(Alconna("sticker-dl"), rule=Rule(is_not_downloading))
patch_matcher(matcher)
lang = LangHelper()


async def download_sticker(event: Optional[Event], bot: Bot, state: T_State, image: Image) -> Optional[bytes]:
    """下载表情包图片的原始数据。

    下载失败时返回 ``None``，由调用方决定是否退回为直接转发原始消息段。
    """
    try:
        return await image_fetch(event, bot, state, image)  # type: ignore[arg-type]
    except Exception:
        logger.opt(exception=True).warning("下载表情包失败")
        return None


async def echo_images(waiter: Waiter, event: Optional[Event], bot: Bot, state: T_State, images: UniMessage) -> None:
    """把用户发送的表情包原样发回当前会话。"""
    message = UniMessage()
    for image in images:
        raw = await download_sticker(event, bot, state, image)
        if raw is None:
            # 下载失败时直接转发原始消息段，尽量保证用户仍能拿到表情包
            message.append(image)
        else:
            message.image(raw=raw)
    await waiter.send_message(message)


async def run_downloader(bot: Bot, state: T_State, user_id: str) -> NoReturn:
    """连续使用 larkuser 的 prompt 接收表情包，直到收到非图片消息。"""
    event: Optional[Event] = None
    while True:
        waiter = Waiter(UniMessage(await lang.text("prompt", user_id)), user_id, event=event)
        try:
            await waiter.wait(timeout=PROMPT_TIMEOUT, auto_finish=False)
        except TimeoutError:
            await waiter.finish("timeout", user_id)
        event = waiter.get_event()
        images = waiter.get().get(Image)
        if not images:
            await waiter.finish("quit", user_id)
        await echo_images(waiter, event, bot, state, images)


@matcher.handle()
async def handle_sticker_dl(bot: Bot, state: T_State, user_id: str = get_user_id()) -> None:
    active_users.add(user_id)
    try:
        await run_downloader(bot, state, user_id)
    finally:
        active_users.discard(user_id)
