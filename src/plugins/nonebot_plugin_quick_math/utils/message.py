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

import asyncio
from typing import Literal, Optional, overload

from nonebot.adapters import Event
from nonebot_plugin_alconna import UniMessage

from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkuser.exceptions import PromptTimeout
from nonebot_plugin_quick_math.__main__ import lang, quick_math
from nonebot_plugin_quick_math.config import config
from nonebot_plugin_quick_math.types import QuestionData, ReplyType, ExtendReplyType


@overload
async def wait_answer(
    question: QuestionData,
    image: UniMessage,
    user_id: str,
    events: Optional[list[Event]] = None,
    enable_leave_command: Literal[False] = False,
) -> ReplyType: ...


@overload
async def wait_answer(
    question: QuestionData,
    image: UniMessage,
    user_id: str,
    events: Optional[list[Event]] = None,
    enable_leave_command: Literal[True] = False,
) -> ReplyType | ExtendReplyType: ...


async def wait_answer(
    question: QuestionData,
    image: UniMessage,
    user_id: str,
    events: Optional[list[Event]] = None,
    enable_leave_command: bool = False,
    allow_quit: bool = True,
    ignore_error_details: bool = False,
) -> ReplyType | ExtendReplyType:
    message = image
    for i in range(config.qm_retry_count + 1):
        try:
            r: str = await prompt(
                message,
                user_id,
                timeout=question["limit_in_sec"],
                event=events[-1] if events else None,
                events=events,
                # 允许退出指令（禅模式）时禁用 prompt 的 q 快捷退出：
                # 否则输入 q 会以 FinishedException 直接结束整个会话，导致无法结算积分
                allow_quit=allow_quit and not enable_leave_command,
                # 超时以 PromptTimeout 返回 ReplyType.TIMEOUT 交给会话结算，
                # 避免 FinishedException 中断会话导致结算卡片不发送
                ignore_error_details=ignore_error_details,
            )
        except PromptTimeout:
            return ReplyType.TIMEOUT
        if r.lower() in ["skip", "tg"]:
            return ReplyType.SKIP
        elif enable_leave_command and r.lower() in ["leave", "quit", "q"]:
            return ExtendReplyType.LEAVE
        elif r.strip().upper() == question["question"]["answer"]:
            # 所有题目都是选择题，answer 是正确选项字母；直接比较字母，忽略大小写与空白
            return ReplyType.RIGHT
        message = UniMessage.text(await lang.text(f"answer.wrong", user_id, config.qm_retry_count - i))
    return ReplyType.WRONG


async def send_start_timer() -> None:
    for sec in range(config.qm_wait_time):
        await quick_math.send(str(config.qm_wait_time - sec))
        await asyncio.sleep(1)
