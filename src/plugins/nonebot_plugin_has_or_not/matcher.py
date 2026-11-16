"""``/has-or-not`` 指令与“三分钟无消息”的活跃度监听。"""

from __future__ import annotations

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkutils import get_group_id, get_user_id

from .game import REVEAL_KEYWORDS, RULES_KEYWORD, HasOrNotGame, games, send_rules
from .lang import lang

has_or_not = on_alconna(Alconna("has-or-not", Args["guess?", str]), aliases={"有无有无"})
patch_matcher(has_or_not)

# 任何会话消息都刷新活跃时间，用于“三分钟没有任何消息时自动公布答案”。
# 放在最高优先级且不阻塞，保证别的指令（block=True）不会让它收不到消息。
activity = on_message(priority=0, block=False)


@activity.handle()
async def record_activity(bot: Bot, event: Event, group_id: str = get_group_id()) -> None:
    game = games.get(group_id)
    if game is not None:
        game.touch(event, bot)


def _plain_text(event: Event) -> str:
    """尽量取出事件里的纯文本；不支持的消息事件返回空串。"""
    getter = getattr(event, "get_plaintext", None)
    if getter is None:
        return ""
    try:
        return str(getter()).strip()
    except Exception:
        return ""


# 不带指令前缀直接发送的中文关键词：按键的指令文本在个别客户端 / 平台上可能
# 丢掉指令前缀，直接发「查看答案 / 结束游戏 / 规则说明」也应当可用。
PLAIN_KEYWORDS = REVEAL_KEYWORDS | {RULES_KEYWORD}


def _is_plain_keyword(event: Event) -> bool:
    return _plain_text(event) in PLAIN_KEYWORDS


plain_command = on_message(priority=1, block=False, rule=_is_plain_keyword)


@plain_command.handle()
async def handle_plain_command(
    bot: Bot,
    event: Event,
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    text = _plain_text(event)
    game = games.get(group_id)
    if game is not None and game.finished:
        games.pop(group_id, None)
        game = None
    if text == RULES_KEYWORD:
        if game is not None:
            game.touch(event, bot)
        await send_rules(bot, event, user_id, game)
        await plain_command.finish()
    if game is None or not game.can_answer(user_id):
        return
    game.touch(event, bot)
    await game.reveal_now()


@has_or_not.handle()
async def handle_has_or_not(
    bot: Bot,
    event: Event,
    guess: Match[str],
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    text = guess.result.strip() if guess.available else ""
    game = games.get(group_id)
    if game is not None and game.finished:
        games.pop(group_id, None)
        game = None
    # 规则说明与是否在局中无关，也不会消耗作答次数
    if text == RULES_KEYWORD:
        if game is not None:
            game.touch(event, bot)
        await send_rules(bot, event, user_id, game)
        await has_or_not.finish()
    # 查看答案直接在处理器里结算，不再依赖后台循环，保证按键立刻有回应
    if text in REVEAL_KEYWORDS:
        if game is None:
            await has_or_not.finish(await lang.text("game.not_playing_start", user_id))
        if not game.can_answer(user_id):
            await has_or_not.finish(await lang.text("game.only_owner", user_id))
        game.touch(event, bot)
        await game.reveal_now()
        await has_or_not.finish()
    if game is None:
        if text:
            await has_or_not.finish(await lang.text("game.not_playing_start", user_id))
        game = HasOrNotGame(group_id, user_id, bot, event)
        game.start()
        await has_or_not.finish()
    if not text:
        await has_or_not.finish(await lang.text("game.already_playing", user_id))
    if game.question is None:
        await has_or_not.finish(await lang.text("game.preparing_short", user_id))
    if not game.can_answer(user_id):
        await has_or_not.finish(await lang.text("game.only_owner", user_id))
    game.submit_guess(user_id, text, event, bot)
    await has_or_not.finish()
