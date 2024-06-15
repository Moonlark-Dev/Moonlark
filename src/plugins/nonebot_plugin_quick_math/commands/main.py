from datetime import datetime
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_waiter import prompt_until
import re

from ..utils.image import generate_image
from ..config import config
from ..utils.generator import generate_question, get_max_level
from ..types import QuestionData
import asyncio
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang, quick_math


async def get_question(max_level: int, user_id: str, answered: int, point: int) -> tuple[UniMessage, QuestionData]:
    question = await generate_question(user_id, max_level)
    return (
        UniMessage().image(
            raw=await generate_image(
                user_id, question["question"]["question"], answered, question["limit_in_sec"], question["level"], point
            )
        ),
        question,
    )


def get_point(question: QuestionData, start_time: datetime) -> int:
    used_time = (datetime.now() - start_time).total_seconds()
    return round(question["max_point"] / question["limit_in_sec"] * (question["limit_in_sec"] - used_time))


@quick_math.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    point = 0
    answered = 0
    max_level = 1
    await lang.send("main.wait", user_id, config.qm_wait_time)
    await asyncio.sleep(config.qm_wait_time)
    while True:
        image, question = await get_question(max_level, user_id, answered, point)
        send_time = datetime.now()
        resp = await prompt_until(
            await image.export(),
            lambda msg: bool(re.match(f"^{question['question']['answer']}$", msg.extract_plain_text())),
            timeout=question["limit_in_sec"],
            retry=config.qm_retry_count,
            retry_prompt=await lang.text(f"answer.wrong", user_id),
            timeout_prompt=await lang.text("main.timeout", user_id, point, answered),
            limited_prompt=await lang.text("main.wrong", user_id, point, answered),
        )
        if resp is None:
            break
        answered += 1
        add_point = get_point(question, send_time)
        point += add_point
        await lang.send("answer.right", user_id, add_point)
        if answered % config.qm_change_max_level_count == 0 and max_level != get_max_level():
            max_level += 1
