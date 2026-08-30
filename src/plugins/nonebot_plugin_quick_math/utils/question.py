from typing import Optional

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage

from ..__main__ import lang
from ..config import config
from ..types import QuestionData
from .generator import generate_question
from .image import generate_image
from .latex import latex_to_plain


async def get_question(
    bot: Bot,
    level: int,
    user_id: str,
    answered: int,
    point: int,
    total_skipping_count: int,
    skipped_question: int,
    override_time_limitation: Optional[float] = None,
    qq_user_id: Optional[str] = None,
    enable_leave_button: bool = False,
) -> tuple[UniMessage, QuestionData]:
    question = await generate_question(user_id, level)
    question["limit_in_sec"] = max(
        config.qm_min_limit, round(override_time_limitation or question["limit_in_sec"] * 0.8 ** (point // 250))
    )
    if isinstance(bot, QQBot):
        return await build_markdown_message(
            user_id,
            question,
            answered,
            point,
            total_skipping_count,
            skipped_question,
            qq_user_id,
            enable_leave_button,
        )
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


async def build_markdown_message(
    user_id: str,
    question: QuestionData,
    answered: int,
    point: int,
    total_skipping_count: int,
    skipped_question: int,
    qq_user_id: Optional[str] = None,
    enable_leave_button: bool = False,
) -> tuple[UniMessage, QuestionData]:
    """构建 QQ 官方机器人的 markdown 题目卡片，并附带操作按钮。"""
    content = await lang.text(
        "main.markdown",
        user_id,
        latex_to_plain(question["question"]["question"]),
        answered,
        question["limit_in_sec"],
        question["level"],
        point,
        skipped_question,
        total_skipping_count,
    )
    if qq_user_id:
        content = f'<qqbot-at-user id="{qq_user_id}" />\n' + content
    message = UniMessage().style(content, "markdown")
    buttons: list[Button] = []
    if total_skipping_count > skipped_question:
        buttons.append(Button("enter", await lang.text("button.skip", user_id), text="skip"))
    if enable_leave_button:
        buttons.append(Button("enter", await lang.text("button.leave", user_id), text="leave"))
    if buttons:
        message.keyboard(*buttons)
    return message, question
