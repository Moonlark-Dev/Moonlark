"""``/has-or-not`` 指令与“三分钟无消息”的活跃度监听。"""

from __future__ import annotations

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkutils import get_group_id, get_user_id

from .game import REVEAL_KEYWORD, HasOrNotGame, games
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


@has_or_not.handle()
async def handle_has_or_not(
    bot: Bot,
    event: Event,
    guess: Match[str],
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    game = games.get(group_id)
    text = guess.result.strip() if guess.available else ""
    if game is None:
        if text:
            await has_or_not.finish(await lang.text("game.not_playing_start", user_id))
        game = HasOrNotGame(group_id, user_id, bot, event)
        game.start()
        await has_or_not.finish()
    if game.finished:
        games.pop(group_id, None)
        await has_or_not.finish(await lang.text("game.not_playing_start", user_id))
    if text == REVEAL_KEYWORD:
        if game.question is None:
            await has_or_not.finish(await lang.text("game.preparing_short", user_id))
        game.request_reveal(event, bot)
        await has_or_not.finish()
    if not text:
        await has_or_not.finish(await lang.text("game.already_playing", user_id))
    if game.question is None:
        await has_or_not.finish(await lang.text("game.preparing_short", user_id))
    if not game.can_answer(user_id):
        await has_or_not.finish(await lang.text("game.only_owner", user_id))
    game.submit_guess(user_id, text, event, bot)
    await has_or_not.finish()
