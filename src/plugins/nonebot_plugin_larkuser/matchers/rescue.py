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
from nonebot.adapters.qq.bot import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, At, Button, Match, UniMessage, on_alconna
from nonebot_plugin_larkutils import get_main_account, get_user_id, is_private_message

from ..lang import lang
from ..utils.downed import RESCUE_COST, RescueResult, process_rescue
from ..utils.matcher import patch_matcher
from ..utils.nickname import get_nickname
from ..utils.user import get_user
from ..utils.waiter import prompt

rescue = patch_matcher(on_alconna(Alconna("rescue", Args["target", At])))


async def build_pay_message(bot: Bot, user_id: str, nickname: str) -> str | UniMessage:
    """构建支付方选择提示。

    QQ 官方机器人附带 由我支付/由对方支付/取消 三个按钮（an ``enter`` 按钮会把
    ``text`` 原样发回聊天，由 prompt 等待器接收），其他平台保持纯文本提示。
    """
    if not isinstance(bot, QQBot):
        return await lang.text("rescue.pay_prompt", user_id, nickname, RESCUE_COST, nickname)
    return (
        UniMessage()
        .style(
            await lang.text("rescue.pay_prompt_markdown", user_id, nickname, RESCUE_COST, nickname),
            "markdown",
        )
        .keyboard(
            Button("enter", await lang.text("rescue.button_rescuer_pay", user_id), text="1"),
            Button("enter", await lang.text("rescue.button_target_pay", user_id, nickname), text="2"),
            Button("enter", await lang.text("rescue.button_quit", user_id), text="q"),
        )
    )


@rescue.handle()
async def _(
    bot: Bot,
    event: Event,
    target: Match[At],
    user_id: str = get_user_id(),
    is_c2c: bool = is_private_message(),
) -> None:
    if is_c2c:
        await lang.finish("rescue.group_only", user_id)
    if not target.available:
        await lang.finish("rescue.no_target", user_id)
    target_adapter_id = target.result.target
    target_id = await get_main_account(target_adapter_id)
    nickname = await get_nickname(target_adapter_id, bot, event)
    rescuer = await get_user(user_id)
    downed_user = await get_user(target_id)
    pay_prompt = await build_pay_message(bot, user_id, nickname)
    choice = await prompt(
        pay_prompt,
        user_id,
        checker=lambda text: text in {"1", "2"},
        retry=3,
        event=event,
    )
    result = await process_rescue(rescuer, downed_user, choice == "1")
    if result == RescueResult.NOT_DOWNED:
        await lang.finish("rescue.not_downed", user_id, nickname)
    elif result == RescueResult.INSUFFICIENT_VIMCOIN:
        await lang.finish("rescue.insufficient", user_id, RESCUE_COST)
    elif result == RescueResult.TARGET_INSUFFICIENT_VIMCOIN:
        await lang.finish("rescue.target_insufficient", user_id, nickname, RESCUE_COST)
    await lang.finish("rescue.success", user_id, nickname)
