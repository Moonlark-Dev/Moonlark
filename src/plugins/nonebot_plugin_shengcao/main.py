import json
import random
from pathlib import Path
from typing import Literal

import jieba
from nonebot import on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.adapters.qq import Bot as QQBot
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import escape_markdown, get_user_id, review_text
from nonebot_plugin_larkutils.command import get_command_prefix

lang = LangHelper()

grass_cmd = on_command("grass")
grass_fury_cmd = on_command("grass-fury")
grass_furry_cmd = on_command("grass-furry")

# 福瑞彩蛋：额外的替换词典（"我" -> "本兽"，常见语气词 -> "嗷呜~"）
_FURRY_PARTICLES = {
    "啊",
    "呀",
    "哦",
    "噢",
    "嗯",
    "唔",
    "哈",
    "嘿",
    "哟",
    "哎",
    "唉",
    "啦",
    "嘛",
    "呢",
    "吧",
    "哇",
    "呜",
    "嘤",
    "哒",
    "哈哈",
    "呵呵",
    "嘿嘿",
    "嘻嘻",
    "呜呜",
    "哎呀",
}
FURRY_DICT = {"我": "本兽", **dict.fromkeys(_FURRY_PARTICLES, "嗷呜~")}

GrassMode = Literal["grass", "fury", "furry"]

_dict_data: dict = {}


def _load_dict() -> None:
    global _dict_data
    path = Path(__file__).parent / "data" / "shengcao_dict.json"
    with path.open("r", encoding="utf-8") as f:
        _dict_data = json.load(f)


_load_dict()


def shengcao_text(text: str, furrified: bool = False) -> str:
    words = list(jieba.cut(text))
    result = []
    for w in words:
        if furrified and w in FURRY_DICT:
            result.append(FURRY_DICT[w])
            continue
        if w.strip() and w in _dict_data:
            entry = _dict_data[w]
            same = entry.get("same_word", [])
            similar = entry.get("similar_word", [])
            if same and similar:
                pool = same if random.random() < 0.6 else similar
            elif same:
                pool = same
            elif similar:
                pool = similar
            else:
                pool = []
            if pool:
                result.append(random.choice(pool))
            else:
                result.append(w)
        else:
            result.append(w)
    return "".join(result)


def fury_text(text: str) -> str:
    """狂怒模式：尽可能全量替换所有文本。

    没有随机是否替换机制，也没有按释义来源（同义/近义）分配替换概率的机制，
    每个命中词典的词一律合并释义池后取首个结果进行替换。
    """
    words = list(jieba.cut(text))
    result = []
    for w in words:
        if w.strip() and w in _dict_data:
            entry = _dict_data[w]
            pool = [*entry.get("same_word", []), *entry.get("similar_word", [])]
            if pool:
                result.append(pool[0])
                continue
        result.append(w)
    return "".join(result)


async def _build_qq_message(user_id: str, output_text: str, original_text: str, mode: GrassMode) -> UniMessage:
    """构建 QQ 官方机器人的 markdown + 键盘消息。

    - 生草结果以 markdown 渲染，需先转义特殊字符
    - 按钮 "再试一次" 重新生草，按钮 "狂怒模式" 切换到全量替换
    - 福瑞彩蛋下按钮文案替换为 UwU / OwO，再试一次切回 grass-furry
    """
    prefix = get_command_prefix()
    retry_label = "UwU" if mode == "furry" else await lang.text("button.retry", user_id)
    fury_label = "OwO" if mode == "furry" else await lang.text("button.fury", user_id)
    retry_command = "grass-furry" if mode == "furry" else "grass"
    return (
        UniMessage()
        .style(f'<qqbot-at-user id="{user_id}" />{escape_markdown(output_text)}', "markdown")
        .keyboard(
            Button("enter", retry_label, text=f"{prefix}{retry_command} {original_text}"),
            Button("enter", fury_label, text=f"{prefix}grass-fury {original_text}"),
        )
    )


async def _finish_result(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    user_id: str,
    output_text: str,
    original_text: str,
    mode: GrassMode,
) -> None:
    if isinstance(bot, QQBot):
        message = await _build_qq_message(user_id, output_text, original_text, mode)
        await message.send(target=event, bot=bot)
        await matcher.finish()
        return
    await lang.finish("result", user_id, output_text)


async def _process_grass(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    user_id: str,
    text: str,
    mode: GrassMode,
) -> None:
    if mode == "fury":
        output_text = fury_text(text)
    elif mode == "furry":
        output_text = shengcao_text(text, furrified=True) + "🐾"
    else:
        output_text = shengcao_text(text)
    if not (await review_text(output_text))["compliance"]:
        await lang.finish("review_failed", user_id)
    await _finish_result(matcher, bot, event, user_id, output_text, text, mode)


@grass_cmd.handle()
async def _grass_handler(bot: Bot, event: Event, user_id: str = get_user_id(), message: Message = CommandArg()) -> None:
    text = message.extract_plain_text()
    if not text or not text.strip():
        await lang.finish("empty", user_id)
    await _process_grass(grass_cmd, bot, event, user_id, text, "grass")


@grass_fury_cmd.handle()
async def _grass_fury_handler(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    message: Message = CommandArg(),
) -> None:
    text = message.extract_plain_text()
    if not text or not text.strip():
        await lang.finish("empty", user_id)
    await _process_grass(grass_fury_cmd, bot, event, user_id, text, "fury")


@grass_furry_cmd.handle()
async def _grass_furry_handler(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    message: Message = CommandArg(),
) -> None:
    text = message.extract_plain_text()
    if not text or not text.strip():
        await lang.finish("empty", user_id)
    await _process_grass(grass_furry_cmd, bot, event, user_id, text, "furry")
