from datetime import datetime
from typing import Optional

from nonebot.adapters import Message
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
import re

from nonebot_plugin_achievement.utils.unlock import unlock_achievement

from ..types import QuestionData
from ..utils.achievement import get_achievement_location, update_achievements_status

from ..utils.point import get_point
from ..utils.question import get_question

from ..utils.user import update_user_data
from ..config import config
from ..utils.generator import get_max_level
import asyncio
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_larkuser.utils.waiter import prompt
from ..__main__ import lang, quick_math
from nonebot_plugin_larkuser.exceptions import PromptTimeout
from enum import Enum


class ReplyType(Enum):
    RIGHT = 0
    TIMEOUT = 1
    WRONG = 2
    SKIP = 3


async def wait_answer(question: QuestionData, image: UniMessage, user_id: str) -> ReplyType:
    message = image
    for i in range(config.qm_retry_count + 1):
        try:
            r: str = await prompt(message, user_id, timeout=question["limit_in_sec"])
        except PromptTimeout:
            return ReplyType.TIMEOUT
        if r.lower() in ["skip", "tg"]:
            return ReplyType.SKIP
        elif await question["question"]["answer"](r):
            return ReplyType.RIGHT
        message = UniMessage.text(await lang.text(f"answer.wrong", user_id, config.qm_retry_count - i))
    return ReplyType.WRONG


@quick_math.assign("$main")
async def handle(max_level: int = 1, user_id: str = get_user_id()) -> None:
    point = 0
    answered = 0
    if max_level < 1 or max_level > get_max_level():
        max_level = 1
    total_skipping_count = 1
    skipped_question = 0
    is_respawned = False
    total_answered = 0

    for sec in range(config.qm_wait_time):
        await quick_math.send(str(config.qm_wait_time - sec))
        await asyncio.sleep(1)
    start_time = datetime.now()
    while True:
        image, question = await get_question(
            max_level, user_id, answered, point, total_skipping_count, skipped_question
        )
        send_time = datetime.now()
        resp = await wait_answer(question, image, user_id)
        total_answered += 1
        if resp == ReplyType.TIMEOUT or resp == ReplyType.WRONG:
            end_time = datetime.now()
            if point >= 400 and not is_respawned:
                try:
                    respawn: str = await prompt(
                        await lang.text("main.respawn_prompt", user_id, point // 2), user_id, timeout=20
                    )
                except PromptTimeout:
                    break
                if respawn.startswith("y"):
                    point -= point // 2
                    is_respawned = True
                    continue
                break
            break
        elif resp == ReplyType.SKIP and total_skipping_count > skipped_question:
            skipped_question += 1
            point += get_point(question, send_time) // 2
            await lang.send("main.skipped", user_id)
        else:
            if question["level"] == 7:
                await unlock_achievement(get_achievement_location("calculus"), user_id)
            add_point = get_point(question, send_time)
            if max_level > 1:
                add_point = int(add_point * 0.8)
            answered += 1
            point += add_point
            await lang.send("answer.right", user_id, add_point)
        if answered % config.qm_change_max_level_count == 0 and max_level != get_max_level():
            max_level += 1
        if point >= 200 * total_skipping_count:
            total_skipping_count += 1
    total_seconds = (end_time - start_time).total_seconds()
    diff, record = await update_user_data(user_id, point)
    if answered == 0:
        await quick_math.finish()
    await update_achievements_status(user_id, answered, point, answered / total_answered, skipped_question)
    await quick_math.finish(
        UniMessage().image(
            raw=await md_to_pic(
                await lang.text(
                    "main.checkout",
                    user_id,
                    answered,
                    int(total_seconds // 60),
                    total_seconds % 60,
                    point,
                    skipped_question,
                    total_seconds / answered,
                    point / answered,
                    point / total_seconds,
                    answered / total_answered * 100,
                    record,
                    point,
                    diff,
                )
            )
        )
    )


@quick_math.assign("max_level")
async def _(max_level: int, user_id: str = get_user_id()) -> None:
    await handle(max_level, user_id)
