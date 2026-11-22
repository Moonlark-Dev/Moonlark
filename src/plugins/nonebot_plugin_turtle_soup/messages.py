"""渲染海龟汤的各种回复：QQ 官方机器人用 Markdown + 快捷按钮，其他适配器退回纯文本。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nonebot_plugin_alconna import Button
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import escape_markdown
from nonebot_plugin_larkutils.command import get_command_prefix

from .config import config
from .lang import lang

if TYPE_CHECKING:
    from .types import EndOutcome, HintOutcome, Puzzle

COMMAND = "turtle-soup"


@dataclass(slots=True)
class Rendered:
    """一条待发送的回复：纯文本、Markdown 与快捷按钮。"""

    plain: str
    markdown: str
    buttons: list[Button] = field(default_factory=list)

    @property
    def row(self) -> int | None:
        """按钮超过两个时排成两列，避免 QQ 按钮标签被截断。"""
        return 2 if len(self.buttons) > 2 else None


async def in_game_buttons(user_id: str) -> list[Button]:
    """游戏进行中的快捷按钮：提问用 input，其余都是完整指令。"""
    prefix = get_command_prefix()
    return [
        # 提问需要玩家输入自由文本：input 会把指令前缀预填进输入框，不直接发送
        Button("input", await lang.text("button.ask", user_id), text=f"{prefix}{COMMAND} "),
        Button("enter", await lang.text("button.progress", user_id), text=f"{prefix}{COMMAND} progress"),
        Button("enter", await lang.text("button.hint", user_id), text=f"{prefix}{COMMAND} hint"),
        Button("enter", await lang.text("button.give-up", user_id), text=f"{prefix}{COMMAND} give-up"),
    ]


async def home_buttons(user_id: str) -> list[Button]:
    """没有进行中的对局时：开始一局 / 查看排行榜。"""
    prefix = get_command_prefix()
    return [
        Button("enter", await lang.text("button.again", user_id), text=f"{prefix}{COMMAND}"),
        Button("enter", await lang.text("button.rank", user_id), text=f"{prefix}{COMMAND} rank"),
    ]


async def _fields(
    user_id: str,
    puzzle: Puzzle,
    *,
    percent: int,
    asked: int,
    question: str = "",
    answer: str = "",
) -> list[tuple[str, str]]:
    fields = [
        (await lang.text("label.title", user_id), puzzle.title),
        (await lang.text("label.puzzle", user_id), puzzle.puzzle_setting),
    ]
    if question:
        fields.append((await lang.text("label.question", user_id), question))
    if answer:
        fields.append((await lang.text("label.answer", user_id), answer))
    fields.extend(
        [
            (await lang.text("label.progress", user_id), f"{percent}%"),
            (
                await lang.text("label.asked", user_id),
                f"{asked}/{max(1, config.turtle_soup_max_questions)}",
            ),
        ],
    )
    return fields


def _render_fields(title: str, fields: list[tuple[str, str]], footer: str = "") -> tuple[str, str]:
    """把标题 + 若干「标签：内容」渲染成（纯文本, Markdown）。"""
    plain = [title]
    markdown = [f"### {title}"]
    for label, value in fields:
        plain.append(f"{label}：{value}")
        markdown.append(f"**{label}**：{escape_markdown(str(value))}")
    if footer:
        plain.append(footer)
        markdown.append(footer)
    return "\n".join(plain), "\n\n".join(markdown)


async def build_start_message(puzzle: Puzzle, user_id: str) -> Rendered:
    title = await lang.text("announce.start", user_id)
    fields = await _fields(user_id, puzzle, percent=0, asked=0)
    footer = await lang.text("message.start_hint", user_id)
    plain, markdown = _render_fields(title, fields, footer)
    return Rendered(plain=plain, markdown=markdown, buttons=await in_game_buttons(user_id))


async def build_ask_message(
    puzzle: Puzzle,
    user_id: str,
    *,
    question: str,
    answer: str,
    percent: int,
    asked: int,
) -> Rendered:
    title = await lang.text("announce.ask", user_id)
    fields = await _fields(user_id, puzzle, percent=percent, asked=asked, question=question, answer=answer)
    footer = await lang.text("message.ask_hint", user_id) if asked < max(1, config.turtle_soup_max_questions) else ""
    plain, markdown = _render_fields(title, fields, footer)
    return Rendered(plain=plain, markdown=markdown, buttons=await in_game_buttons(user_id))


async def build_progress_message(
    puzzle: Puzzle,
    user_id: str,
    *,
    percent: int,
    asked: int,
    recent: list[tuple[str, str]],
) -> Rendered:
    title = await lang.text("announce.progress", user_id)
    fields = await _fields(user_id, puzzle, percent=percent, asked=asked)
    lines_plain: list[str] = []
    lines_markdown: list[str] = []
    if recent:
        for index, (question, answer) in enumerate(recent, 1):
            lines_plain.append(f"{index}. Q: {question} / A: {answer}")
            lines_markdown.append(f"{index}. **Q**：{escape_markdown(question)} **A**：{escape_markdown(answer)}")
    footer = await lang.text("message.ask_hint", user_id)
    plain, markdown = _render_fields(title, fields)
    plain = "\n".join([plain, *lines_plain, footer])
    markdown = "\n\n".join([markdown, *lines_markdown, footer])
    return Rendered(plain=plain, markdown=markdown, buttons=await in_game_buttons(user_id))


async def build_hint_message(user_id: str, hint: HintOutcome) -> Rendered:
    title = await lang.text("announce.hint", user_id)
    footer = await lang.text("message.ask_hint", user_id)
    if hint.finished:
        text = await lang.text("status.all_hints", user_id, hint.total)
        plain = f"{title}\n{text}\n{footer}"
        markdown = f"### {title}\n\n{text}\n\n{footer}"
        return Rendered(plain=plain, markdown=markdown, buttons=await in_game_buttons(user_id))
    label = await lang.text("message.hint_line", user_id, hint.current, hint.total)
    plain, markdown = _render_fields(title, [(label, hint.hint)], footer)
    return Rendered(plain=plain, markdown=markdown, buttons=await in_game_buttons(user_id))


async def build_end_message(end: EndOutcome, user_id: str) -> Rendered:
    announce = await lang.text("announce.solved" if end.solved else "announce.given-up", user_id)
    lines_plain: list[str] = [announce]
    lines_markdown: list[str] = [f"### {announce}"]

    async def add(label_key: str, value: str) -> None:
        label = await lang.text(label_key, user_id)
        lines_plain.append(f"{label}：{value}")
        lines_markdown.append(f"**{label}**：{escape_markdown(value)}")

    await add("label.title", end.title)
    await add("label.puzzle", end.puzzle_setting)
    await add("label.solution", end.solution)
    hints = end.supplementary_info
    hints_label = await lang.text("label.supplementary", user_id)
    lines_plain.append(f"{hints_label}：")
    lines_plain.extend(f"• {hint}" for hint in hints)
    lines_markdown.append(f"**{hints_label}**：")
    lines_markdown.extend(f"- {escape_markdown(hint)}" for hint in hints)
    await add("label.asked", str(end.asked))
    if end.solved and end.solved_by:
        try:
            nickname = (await get_user(end.solved_by)).get_nickname()
        except Exception:
            nickname = end.solved_by
        await add("label.solved_by", nickname)
    footer = await lang.text("message.end_hint", user_id)
    lines_plain.append(footer)
    lines_markdown.append(footer)
    return Rendered(
        plain="\n".join(lines_plain),
        markdown="\n\n".join(lines_markdown),
        buttons=await home_buttons(user_id),
    )


async def build_no_game_message(user_id: str) -> Rendered:
    title = await lang.text("announce.rules", user_id)
    status = await lang.text("status.not_playing", user_id)
    plain = f"{title}\n{status}"
    markdown = f"### {title}\n\n{status}"
    return Rendered(plain=plain, markdown=markdown, buttons=await home_buttons(user_id))


async def build_already_playing_message(user_id: str) -> Rendered:
    title = await lang.text("announce.start", user_id)
    status = await lang.text("status.already_playing", user_id)
    plain = f"{title}\n{status}"
    markdown = f"### {title}\n\n{status}"
    return Rendered(plain=plain, markdown=markdown, buttons=await in_game_buttons(user_id))


async def build_status_message(user_id: str, text: str, *, in_game: bool) -> Rendered:
    title = await lang.text("announce.ask" if in_game else "announce.rules", user_id)
    plain = f"{title}\n{text}"
    markdown = f"### {title}\n\n{text}"
    buttons = await in_game_buttons(user_id) if in_game else await home_buttons(user_id)
    return Rendered(plain=plain, markdown=markdown, buttons=buttons)


async def build_help_message(user_id: str) -> Rendered:
    title = await lang.text("announce.rules", user_id)
    rules = await lang.text("message.rules", user_id, max(1, config.turtle_soup_max_questions))
    plain = f"{title}\n{rules}"
    markdown = f"### {title}\n\n{rules}"
    return Rendered(plain=plain, markdown=markdown, buttons=await home_buttons(user_id))


async def build_rank_message(
    rows: list[tuple[str, int]],
    user_id: str,
    *,
    my_index: int | None,
    my_count: int,
    limit: int = 10,
) -> Rendered:
    title = await lang.text("announce.rank", user_id)
    if not rows:
        empty = await lang.text("status.rank_empty", user_id)
        plain = f"{title}\n{empty}"
        markdown = f"### {title}\n\n{empty}"
    else:
        plain_lines = [title]
        markdown_lines = [f"### {title}"]
        for index, (nickname, count) in enumerate(rows[:limit], 1):
            item = await lang.text("message.rank_item", user_id, index, nickname, count)
            plain_lines.append(item)
            markdown_lines.append(escape_markdown(item))
        plain = "\n".join(plain_lines)
        markdown = "\n\n".join(markdown_lines)
    if my_index is not None:
        me = await lang.text("message.rank_me", user_id, my_index, my_count)
        plain = f"{plain}\n{me}"
        markdown = f"{markdown}\n\n{me}"
    return Rendered(plain=plain, markdown=markdown, buttons=await home_buttons(user_id))
