from datetime import datetime
from nonebot.adapters import Message
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_waiter import prompt_until
import re

from ...nonebot_plugin_achievement.utils.unlock import unlock_achievement

from ..utils.achievement import get_achievement_location, update_achievements_status

from ..utils.point import get_point
from ..utils.question import get_question

from ..utils.user import update_user_data
from ..config import config
from ..utils.generator import get_max_level
import asyncio
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang, quick_math


@quick_math.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    point = 0
    answered = 0
    max_level = 1
    total_skipping_count = 1
    skipped_question = 0
    total_answered = 0

    def check_input(msg: Message) -> bool:
        nonlocal total_answered
        total_answered += 1
        return bool(
            re.match(f"^{question['question']['answer']}$", message := msg.extract_plain_text())
            or ((message.lower() == "skip" or message.lower == "tg") and total_skipping_count > skipped_question)
        )

    await lang.send("main.wait", user_id, config.qm_wait_time)
    await asyncio.sleep(config.qm_wait_time)
    start_time = datetime.now()
    while True:
        image, question = await get_question(
            max_level, user_id, answered, point, total_skipping_count, skipped_question
        )
        send_time = datetime.now()
        resp = await prompt_until(
            await image.export(),
            check_input,
            timeout=question["limit_in_sec"],
            retry=config.qm_retry_count,
            retry_prompt=await lang.text(f"answer.wrong", user_id),
            timeout_prompt=await lang.text("main.timeout", user_id),
            limited_prompt=await lang.text("main.wrong", user_id),
        )
        if resp is None:
            end_time = datetime.now()
            if point > 300:
                point -= 300
                continue
            else:
                break
        elif resp.extract_plain_text().lower() == "skip" or resp.extract_plain_text().lower == "tg":
            skipped_question += 1
            point += get_point(question, send_time) // 2
            await lang.send("main.skipped", user_id)
        else:
            if question["level"] == 7:
                await unlock_achievement(get_achievement_location("calculus"), user_id)
            add_point = get_point(question, send_time)
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
