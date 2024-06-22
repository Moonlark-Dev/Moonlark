from nonebot_plugin_htmlrender import md_to_pic
from ..__main__ import lang


async def generate_image(
    user_id: str,
    question: str,
    answered: int,
    limit_in_sec: int,
    level: int,
    current_point: int,
    total_skipping_count: int,
    skipped_question: int,
) -> bytes:
    markdown = await lang.text(
        "main.markdown",
        user_id,
        question,
        answered,
        limit_in_sec,
        level,
        current_point,
        skipped_question,
        total_skipping_count,
    )
    return await md_to_pic(markdown, type="jpeg")
