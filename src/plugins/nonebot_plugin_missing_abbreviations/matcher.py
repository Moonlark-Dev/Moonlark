"""``/missing-abbreviations`` 指令与“三分钟无消息”的活跃度监听。"""

from typing import Optional

from arclet.alconna import AllParam, namespace
from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, Match, UniMessage, on_alconna
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkutils import get_group_id, get_user_id

from .game import HINT_KEYWORDS, REVEAL_KEYWORDS, RULES_KEYWORD, MissingAbbreviationsGame, games, send_rules
from .lang import lang

with namespace("missing_abbreviations") as _ns:
    _ns.disable_builtin_options = {"shortcut", "help", "completion"}
    _alc = Alconna("missing-abbreviations", Args["guess?", AllParam])

missing_abbreviations = on_alconna(_alc, aliases={"缩略", "ma"})
patch_matcher(missing_abbreviations)

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


def _extract_guess_text(guess: Match[object]) -> str:
    """从 Alconna AllParam 匹配结果中提取原始作答文本（保留引号、连字符与空格）。"""
    if not guess.available or guess.result is None:
        return ""
    raw = guess.result
    if isinstance(raw, UniMessage):
        return raw.extract_plain_text().strip()
    if isinstance(raw, tuple):
        return " ".join(str(part) for part in raw).strip()
    return str(raw).strip()


def _get_active_game(group_id: str) -> Optional[MissingAbbreviationsGame]:
    game = games.get(group_id)
    if game is not None and game.finished:
        if games.get(group_id) is game:
            games.pop(group_id, None)
        return None
    return game


# 不带指令前缀直接发送的中文关键词：按键的指令文本在个别客户端 / 平台上可能丢掉指令前缀。
# 注意：仅在当前会话确实有进行中的「缩略」游戏时才响应，避免与其他插件或日常聊天冲突。
PLAIN_KEYWORDS = HINT_KEYWORDS | REVEAL_KEYWORDS | {RULES_KEYWORD}


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
    game = _get_active_game(group_id)
    if game is None:
        return
    text = _plain_text(event)
    if text == RULES_KEYWORD:
        plain_command.stop_propagation()
        game.touch(event, bot)
        await send_rules(bot, event, user_id, game)
        await plain_command.finish()
    if not game.can_answer(user_id):
        return
    plain_command.stop_propagation()
    game.touch(event, bot)
    if text in HINT_KEYWORDS:
        await game.unlock_hint()
        await plain_command.finish()
    if text in REVEAL_KEYWORDS:
        await game.reveal_now()
        await plain_command.finish()


async def _handle_keyword_action(
    bot: Bot,
    event: Event,
    text: str,
    user_id: str,
    game: Optional[MissingAbbreviationsGame],
) -> bool:
    """处理规则说明、提示、查看答案三类内置子动作；已处理返回 True。"""
    if text == RULES_KEYWORD:
        if game is not None:
            game.touch(event, bot)
        await send_rules(bot, event, user_id, game)
        return True
    if text not in HINT_KEYWORDS and text not in REVEAL_KEYWORDS:
        return False
    if game is None:
        await missing_abbreviations.finish(await lang.text("game.not_playing_start", user_id))
    if not game.can_answer(user_id):
        await missing_abbreviations.finish(await lang.text("game.only_owner", user_id))
    game.touch(event, bot)
    if text in HINT_KEYWORDS:
        await game.unlock_hint()
    else:
        await game.reveal_now()
    return True


@missing_abbreviations.handle()
async def handle_missing_abbreviations(
    bot: Bot,
    event: Event,
    guess: Match[object],
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    text = _extract_guess_text(guess)
    game = _get_active_game(group_id)
    if await _handle_keyword_action(bot, event, text, user_id, game):
        await missing_abbreviations.finish()
    if game is None:
        if text:
            await missing_abbreviations.finish(await lang.text("game.not_playing_start", user_id))
        new_game = MissingAbbreviationsGame(group_id, user_id, bot, event)
        new_game.start()
        await missing_abbreviations.finish()
    if not text:
        await missing_abbreviations.finish(await lang.text("game.already_playing", user_id))
    if game.question is None:
        await missing_abbreviations.finish(await lang.text("game.preparing_short", user_id))
    if not game.can_answer(user_id):
        await missing_abbreviations.finish(await lang.text("game.only_owner", user_id))
    game.submit_guess(user_id, text, event, bot)
    await missing_abbreviations.finish()
