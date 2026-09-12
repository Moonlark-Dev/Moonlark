from typing import Awaitable, Callable, Optional

from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkutils.cache import create_image_markdown

from ..__main__ import lang
from ..config import config
from ..types import QuestionData
from .generator import generate_question
from .image import generate_image
from .latex import ensure_math_mode, latex_to_plain

_OPTION_LETTERS = "ABCDEFGHIJKL"

# 仅一元二次方程（L5）的选项由 sympy 生成 LaTeX（\frac、\sqrt），QQ markdown 不解析
# LaTeX，会把它显示成 "- (9)/(2) - √(57)2" 这类难以辨认的纯文本；因此只有该等级把
# 题目信息渲染成图片，其余等级继续使用纯文本卡片，避免为简单题目平白增加一次浏览器
# 渲染与图床上传。
_QUESTION_IMAGE_LEVELS = frozenset({5})


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


async def build_choices_markdown(user_id: str, options: list[str], to_plain: bool = False) -> str:
    """构建“请选择答案”标题与选项列表的 markdown。

    ``to_plain`` 为 ``True``（回退到纯文本）时把 LaTeX 选项转成可读的普通文本，
    否则把裸 LaTeX 选项包进 ``$...$`` 交给 md_to_pic 渲染成公式。
    """
    transform = latex_to_plain if to_plain else ensure_math_mode
    # 选项要逐行显示：markdown 会把段落内的单个换行折叠成空格，因此渲染图片时用
    # 行尾双空格产生硬换行；回退的纯文本直接交给 QQ markdown，无需硬换行
    separator = "\n" if to_plain else "  \n"
    return await lang.text(
        "main.choices",
        user_id,
        separator.join(
            [
                await lang.text("main.choice_item", user_id, _OPTION_LETTERS[index], transform(option))
                for index, option in enumerate(options)
            ],
        ),
    )


async def build_question_info_markdown(user_id: str, question: QuestionData, to_plain: bool = False) -> str:
    """构建题目信息（题干 + 选项）的 markdown。"""
    content = question["question"]["question"]
    if to_plain:
        content = latex_to_plain(content)
    options = question["question"].get("options") or []
    if len(options) > 1:
        content += "\n\n" + await build_choices_markdown(user_id, options, to_plain=to_plain)
    return content


async def build_question_info(user_id: str, question: QuestionData) -> str:
    """构建 QQ 官方机器人的题目信息。

    一元二次方程（见 ``_QUESTION_IMAGE_LEVELS``）的选项是 LaTeX，直接用 md_to_pic 把
    题目信息（题干 + “请选择答案” + 选项）渲染为图片，再上传图床并返回可供 markdown
    引用的图片代码；图床未配置或渲染失败时回退为 ``latex_to_plain`` 的纯文本。其余
    等级继续使用纯文本题目信息。
    """
    if question["level"] not in _QUESTION_IMAGE_LEVELS:
        return await build_question_info_markdown(user_id, question, to_plain=True)
    markdown = await build_question_info_markdown(user_id, question)
    try:
        image = await create_image_markdown(await md_to_pic(markdown, type="jpeg"))
    except Exception:
        logger.exception("Quick Math 题目信息渲染为图片失败，回退为纯文本")
        return await build_question_info_markdown(user_id, question, to_plain=True)
    return image


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
        "main.qq_markdown",
        user_id,
        await build_question_info(user_id, question),
        answered,
        question["limit_in_sec"],
        question["level"],
        point,
        skipped_question,
        total_skipping_count,
        qq_user_id=qq_user_id,
    )
    message = UniMessage().style(content, "markdown")
    if question["level"] in _QUESTION_IMAGE_LEVELS:
        # 选项原文已随题目信息渲染进图片，按钮只显示并回传选项字母
        buttons: list[Button] = [
            Button("enter", _OPTION_LETTERS[index], text=_OPTION_LETTERS[index]) for index in range(len(options))
        ]
    else:
        # 选项仍以文本显示在卡片里，按钮保留选项原文便于直接辨认；回传的仍是字母，
        # 服务端无需再判定长文本（例如 L7 需要调用 AI 判定），直接按字母取选项即可
        buttons = [
            Button("enter", latex_to_plain(option), text=_OPTION_LETTERS[index]) for index, option in enumerate(options)
        ]
    if total_skipping_count > skipped_question:
        buttons.append(Button("enter", await lang.text("button.skip", user_id), text="skip"))
    if enable_leave_button:
        buttons.append(Button("enter", await lang.text("button.leave", user_id), text="leave"))
    if buttons:
        message.keyboard(*buttons, row=4)
    return message, with_option_letters(question)
