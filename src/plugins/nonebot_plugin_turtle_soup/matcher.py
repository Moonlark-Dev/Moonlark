"""``/turtle-soup`` 指令：开始、提问、进度、提示、重算、放弃与排行榜。

作答方式统一为指令（而不是 @bot）：群里所有人都可以用
``/turtle-soup <问题>`` 提问，QQ 官方机器人的「提问」按钮用 input 类型预填指令前缀，
玩家补上问题再发送。不带参数时没有进行中的对局就开一局，有对局则查看进度。
"""

from __future__ import annotations

from nonebot import logger
from nonebot.adapters import Bot, Event  # ruff: ignore[typing-only-third-party-import]
from nonebot.adapters.qq import Bot as QQBot
from nonebot.exception import FinishedException
from nonebot.matcher import Matcher  # ruff: ignore[typing-only-third-party-import]
from nonebot_plugin_alconna import Alconna, Args, Arparma, MultiVar, UniMessage, on_alconna
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_ranking import generate_image

from .game import (
    GameAlreadyPlayingError,
    GameError,
    GameExpiredError,
    QuestionLimitError,
    abort_game,
    get_active_game,
    start_game,
)
from .judge import JudgeError
from .lang import lang
from .messages import (
    Rendered,
    build_already_playing_message,
    build_ask_message,
    build_end_message,
    build_help_message,
    build_hint_message,
    build_no_game_message,
    build_progress_message,
    build_rank_message,
    build_start_message,
    build_status_message,
)
from .rank import get_rank_display, get_ranking_data
from .types import EndOutcome

COMMAND = "turtle-soup"

START_WORDS = frozenset({"start", "new", "开始", "新游戏", "开局", "开始游戏"})
ASK_WORDS = frozenset({"ask", "提问", "问"})
PROGRESS_WORDS = frozenset({"progress", "进度", "查看进度", "当前进度", "状态"})
HINT_WORDS = frozenset({"hint", "提示", "给个提示", "来个提示"})
RECALCULATE_WORDS = frozenset({"recalculate", "recalc", "重算", "重算进度", "重新计算", "重新计算进度"})
GIVE_UP_WORDS = frozenset({"give-up", "giveup", "放弃", "我放弃", "不玩了", "公布答案", "看答案"})
RANK_WORDS = frozenset({"rank", "排行", "排行榜", "排名"})
HELP_WORDS = frozenset({"help", "帮助", "规则", "规则说明", "玩法", "说明"})

turtle_soup = on_alconna(
    Alconna("turtle-soup", Args["text?", MultiVar(str)]),
    aliases={"海龟汤"},
    use_cmd_start=True,
)
patch_matcher(turtle_soup)


def extract_words(result: Arparma) -> tuple[str, ...]:
    """从 Alconna 解析结果里取出指令后面的词。

    不直接依赖 ``text`` 参数注入：没有参数时 ``MultiVar`` 不会出现在
    ``all_matched_args`` 里，按参数注入会抛 ``TypeMisMatch``。
    """
    raw = result.all_matched_args.get("text")
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    try:
        return tuple(str(word) for word in raw)
    except TypeError:
        return (str(raw),)


def parse_input(words: tuple[str, ...]) -> tuple[str, str]:
    """把指令后面的词解析成（动作, 内容）。

    不认识的首词直接当作问题的一部分，所以 ``/turtle-soup 这个人是故意的吗`` 与
    ``/turtle-soup ask 这个人是故意的吗`` 等价。
    """
    parts = [word.strip() for word in words if word.strip()]
    if not parts:
        return "", ""
    head = parts[0]
    lowered = head.lower()
    rest = " ".join(parts[1:]).strip()
    table: tuple[tuple[frozenset[str], str], ...] = (
        (START_WORDS, "start"),
        (ASK_WORDS, "ask"),
        (PROGRESS_WORDS, "progress"),
        (HINT_WORDS, "hint"),
        (RECALCULATE_WORDS, "recalculate"),
        (GIVE_UP_WORDS, "give-up"),
        (RANK_WORDS, "rank"),
        (HELP_WORDS, "help"),
    )
    for words_set, action in table:
        if lowered in words_set:
            return action, rest
    return "ask", " ".join(parts)


async def send_rendered(matcher: Matcher, bot: Bot, event: Event, rendered: Rendered) -> None:
    """QQ 官方机器人发送 Markdown + 按钮，其他适配器发送纯文本。"""
    if isinstance(bot, QQBot):
        message = UniMessage().style(rendered.markdown, "markdown")
        if rendered.buttons:
            message = message.keyboard(*rendered.buttons, row=rendered.row)
        try:
            await message.send(target=event, bot=bot)
        except Exception:
            logger.opt(exception=True).warning("海龟汤：发送 Markdown 消息失败，回退纯文本")
        else:
            await matcher.finish()
    await matcher.send(rendered.plain, at_sender=True)
    await matcher.finish()


async def _handle_rank(matcher: Matcher, bot: Bot, event: Event, user_id: str) -> None:
    top, my_index, my_count = await get_rank_display(user_id)
    if isinstance(bot, QQBot):
        await send_rendered(
            matcher,
            bot,
            event,
            await build_rank_message(top, user_id, my_index=my_index, my_count=my_count),
        )
        return
    if not top:
        await send_rendered(
            matcher,
            bot,
            event,
            await build_rank_message([], user_id, my_index=None, my_count=0),
        )
        return
    try:
        data = await get_ranking_data()
        image = await generate_image(data, user_id, await lang.text("announce.rank", user_id))
    except Exception:
        logger.opt(exception=True).warning("海龟汤：生成排行榜图片失败，退回文本排行榜")
        await send_rendered(
            matcher,
            bot,
            event,
            await build_rank_message(top, user_id, my_index=my_index, my_count=my_count),
        )
        return
    await matcher.finish(UniMessage().image(raw=image, name="turtle-soup-rank.png"))


async def _handle_start(matcher: Matcher, bot: Bot, event: Event, user_id: str, group_id: str, theme: str) -> None:
    if await get_active_game(group_id) is not None:
        await send_rendered(matcher, bot, event, await build_already_playing_message(user_id))
        return
    await matcher.send(await lang.text("status.generating", user_id))
    try:
        game = await start_game(group_id, user_id, theme)
    except GameAlreadyPlayingError:
        await send_rendered(matcher, bot, event, await build_already_playing_message(user_id))
        return
    except Exception:
        logger.opt(exception=True).error("海龟汤：生成谜题失败")
        await send_rendered(
            matcher,
            bot,
            event,
            await build_status_message(user_id, await lang.text("status.generate_failed", user_id), in_game=False),
        )
        return
    try:
        rendered = await build_start_message(game.puzzle, user_id)
        await send_rendered(matcher, bot, event, rendered)
    except FinishedException:
        raise
    except Exception:
        # 开局消息没能发出去时回滚本局，避免群里被静默屏蔽 36 小时
        logger.opt(exception=True).error("海龟汤：发送开局消息失败，回滚本局")
        await abort_game(game)
        raise


async def _handle_ask(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    user_id: str,
    group_id: str,
    question: str,
) -> None:
    game = await get_active_game(group_id)
    if game is None:
        await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
        return
    if not question:
        await send_rendered(
            matcher,
            bot,
            event,
            await build_status_message(user_id, await lang.text("status.empty_question", user_id), in_game=True),
        )
        return
    if not game.can_ask():
        await send_rendered(
            matcher,
            bot,
            event,
            await build_status_message(
                user_id,
                await lang.text("status.question_limit", user_id, game.max_questions),
                in_game=True,
            ),
        )
        return
    try:
        outcome = await game.ask_question(user_id, question, bot, event)
    except QuestionLimitError:
        await send_rendered(
            matcher,
            bot,
            event,
            await build_status_message(
                user_id,
                await lang.text("status.question_limit", user_id, game.max_questions),
                in_game=True,
            ),
        )
        return
    except JudgeError:
        await send_rendered(
            matcher,
            bot,
            event,
            await build_status_message(user_id, await lang.text("status.judge_failed", user_id), in_game=True),
        )
        return
    except GameExpiredError:
        await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
        return
    except GameError:
        await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
        return
    if outcome.solved:
        end = EndOutcome(
            solved=True,
            percent=outcome.percent,
            asked=outcome.asked,
            title=outcome.title,
            puzzle_setting=outcome.puzzle_setting,
            solution=outcome.solution,
            supplementary_info=outcome.supplementary_info,
            solved_by=user_id,
        )
        await send_rendered(matcher, bot, event, await build_end_message(end, user_id))
        return
    await send_rendered(
        matcher,
        bot,
        event,
        await build_ask_message(
            game.puzzle,
            user_id,
            question=outcome.question,
            answer=outcome.reply,
            percent=outcome.percent,
            asked=outcome.asked,
        ),
    )


@turtle_soup.handle()
async def _(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    result: Arparma,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    action, content = parse_input(extract_words(result))
    if action == "help":
        await send_rendered(matcher, bot, event, await build_help_message(user_id))
        return
    if action == "rank":
        await _handle_rank(matcher, bot, event, user_id)
        return
    if action == "start":
        await _handle_start(matcher, bot, event, user_id, group_id, content)
        return

    game = await get_active_game(group_id)
    if game is None:
        if action == "":
            # 裸指令且没有进行中的对局：开一局（开局按钮发送的就是这条指令）
            await _handle_start(matcher, bot, event, user_id, group_id, "")
            return
        await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
        return

    if action in ("", "progress"):
        recent = [(item.question, item.reply) for item in game.history[-3:]]
        await send_rendered(
            matcher,
            bot,
            event,
            await build_progress_message(
                game.puzzle,
                user_id,
                percent=game.percent,
                asked=game.asked,
                recent=recent,
            ),
        )
        return
    if action == "hint":
        try:
            hint = await game.next_hint()
        except GameError:
            await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
            return
        if hint.total == 0:
            await send_rendered(
                matcher,
                bot,
                event,
                await build_status_message(user_id, await lang.text("status.no_hint", user_id), in_game=True),
            )
            return
        await send_rendered(matcher, bot, event, await build_hint_message(user_id, hint))
        return
    if action == "recalculate":
        await matcher.send(await lang.text("status.recalculating", user_id))
        try:
            percent = await game.recalculate(user_id)
        except JudgeError:
            await send_rendered(
                matcher,
                bot,
                event,
                await build_status_message(
                    user_id,
                    await lang.text("status.recalculate_failed", user_id),
                    in_game=True,
                ),
            )
            return
        except GameError:
            await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
            return
        await send_rendered(
            matcher,
            bot,
            event,
            await build_status_message(
                user_id,
                await lang.text("message.recalculated", user_id, percent),
                in_game=True,
            ),
        )
        return
    if action == "give-up":
        try:
            end = await game.give_up(bot, event)
        except GameError:
            await send_rendered(matcher, bot, event, await build_no_game_message(user_id))
            return
        await send_rendered(matcher, bot, event, await build_end_message(end, user_id))
        return
    await _handle_ask(matcher, bot, event, user_id, group_id, content)
