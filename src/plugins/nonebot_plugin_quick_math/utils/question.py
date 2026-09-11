from typing import Awaitable, Callable, Optional

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage

from ..__main__ import lang
from ..config import config
from ..types import QuestionData
from .generator import generate_question
from .image import generate_image
from .latex import latex_to_plain

_OPTION_LETTERS = "ABCDEFGHIJKL"


def build_option_answer_matcher(
    options: list[str], verify: Callable[[str], Awaitable[bool]]
) -> Callable[[str], Awaitable[bool]]:
    """包装原始判定函数，使选项按钮发送的选项字母（A/B/C/D）也能被直接判定。

    题目卡片上的选项按钮只回传 ``A``/``B``/``C``/``D``，因此这里先把字母翻译回
    对应选项文本再交给原始判定函数，避免把字母送进 AI 判定等慢速路径；用户手动
    输入选项字母或选项原文时同样走这条捷径。
    """

    async def verify_option(string: str) -> bool:
        answer = string.strip()
        if len(answer) == 1:
            index = _OPTION_LETTERS.find(answer.upper())
            if 0 <= index < len(options):
                return await verify(options[index])
        return await verify(string)

    return verify_option


def with_option_letters(question: QuestionData) -> QuestionData:
    """返回一份新的题目数据：选项按钮回传选项字母，而不是选项原文。

    仅在题目带选项（选择题）时包装判定函数；选项原文仍会被翻译回来交给原始
    判定函数判定，保证手输答案的行为不变。
    """
    options = question["question"].get("options") or []
    if len(options) < 2:
        return question
    return {
        **question,
        "question": {
            **question["question"],
            "answer": build_option_answer_matcher(options, question["question"]["answer"]),
        },
    }


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
    """构建 QQ 官方机器人的 markdown 题目卡片，并附带选项/操作按钮。"""
    options = question["question"].get("options") or []
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
    if len(options) > 1:
        choices = await lang.text(
            "main.choices",
            user_id,
            "\n".join(
                [
                    await lang.text("main.choice_item", user_id, _OPTION_LETTERS[index], latex_to_plain(option))
                    for index, option in enumerate(options)
                ],
            ),
        )
        # 在题目文本与“请选择答案”标题之间补空行，否则 ## 标题与题目粘在同一行
        # 导致 QQ markdown 无法识别标题，原样显示 ##
        content += "\n\n" + choices
    if qq_user_id:
        content = f'<qqbot-at-user id="{qq_user_id}" />\n' + content
    message = UniMessage().style(content, "markdown")
    # 按钮显示选项原文，但回传选项字母：服务端无需再判定长文本（例如 L7 需要
    # 调用 AI 判定），直接按字母取选项即可，显著加快答案判定速度
    buttons: list[Button] = [
        Button("enter", latex_to_plain(option), text=_OPTION_LETTERS[index]) for index, option in enumerate(options)
    ]
    if total_skipping_count > skipped_question:
        buttons.append(Button("enter", await lang.text("button.skip", user_id), text="skip"))
    if enable_leave_button:
        buttons.append(Button("enter", await lang.text("button.leave", user_id), text="leave"))
    if buttons:
        message.keyboard(*buttons, row=4)
    return message, with_option_letters(question)
