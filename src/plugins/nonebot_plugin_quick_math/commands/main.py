from datetime import datetime
from nonebot.adapters import Message
from nonebot_plugin_alconna import UniMessage, Match
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_waiter import prompt_until, prompt
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
async def _(start_level: Match[int], user_id: str = get_user_id()) -> None:
    point = 0
    answered = 0
    if start_level.available and 1 <= start_level.result <= get_max_level():
        max_level = start_level.result
    else:
        max_level = 1
    total_skipping_count = 1
    skipped_question = 0
    is_respawned = False
    total_answered = 0

    def check_input(msg: Message) -> bool:
        nonlocal total_answered
        total_answered += 1
        return bool(
            re.match(f"^{question['question']['answer']}$", message := msg.extract_plain_text())
            or (message.lower() in ["skip", "tg"] and total_skipping_count > skipped_question)
        )

    for sec in range(config.qm_wait_time):
        await quick_math.send(str(config.qm_wait_time - sec))
        await asyncio.sleep(1)
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
            if point >= 400 and not is_respawned:
                resp = await prompt(await lang.text("main.respawn_prompt", user_id, point // 2), timeout=20)
                if resp is None or not resp.extract_plain_text().lower().startswith("y"):
                    break
                point -= point // 2
                is_respawned = True
                continue
            break
        elif resp.extract_plain_text().lower() in ["skip", "tg"]:
            skipped_question += 1
            point += get_point(question, send_time) // 2
            await lang.send("main.skipped", user_id)
        else:
            if question["level"] == 7:
                await unlock_achievement(get_achievement_location("calculus"), user_id)
            add_point = get_point(question, send_time)
            if start_level.available and start_level.result > 1:
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
