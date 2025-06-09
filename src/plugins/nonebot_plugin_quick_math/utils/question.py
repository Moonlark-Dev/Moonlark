from ..config import config
from ..types import QuestionData
from .generator import generate_question
from .image import generate_image


from nonebot_plugin_alconna import UniMessage


async def get_question(
    level: int, user_id: str, answered: int, point: int, total_skipping_count: int, skipped_question: int
) -> tuple[UniMessage, QuestionData]:
    question = await generate_question(user_id, level)
    question["limit_in_sec"] = max(config.qm_min_limit, round(question["limit_in_sec"] * 0.8 ** (point // 250)))
    return (
        UniMessage().image(
            raw=await generate_image(
                user_id,
                question["question"]["question"],
                answered,
                question["limit_in_sec"],
                question["level"],
                point,
                total_skipping_count,
                skipped_question,
            ),
            name="image.jpg",
        ),
        question,
    )
