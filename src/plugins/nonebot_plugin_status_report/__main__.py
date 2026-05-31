#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################
import hashlib
import traceback
from datetime import datetime
from typing import cast, Optional, TYPE_CHECKING

from fastapi import FastAPI
from nonebot import get_app, get_loaded_plugins, get_driver
from nonebot.message import run_postprocessor, run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.matcher import AlconnaMatcher
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from nonebot_plugin_bots.__main__ import bots_status
from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_main_account
from nonebot_plugin_render import render_template
from nonebot_plugin_render.render import generate_render_keys
from nonebot.adapters import Event, Bot
from nonebot.matcher import Matcher, matchers
from fastapi import Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select, func, delete
from .config import config
from .matcher import simple_run
from .models import CommandUsage, HandlerResultRecord, ExceptionRecord, OpenAIHistoryRecord
from .types import ExceptionStatus, EventCounter, OpenAIHistory, StatusReport, HandlerResult

if TYPE_CHECKING:
    from nonebot_plugin_openai.types import Messages


lang = LangHelper()

app = cast(FastAPI, get_app())
event_counter = (0, 0)  # total, success

MAX_HANDLER_RESULTS = 20
MAX_EXCEPTIONS = 20
MAX_OPENAI_HISTORY = 20


async def get_command_usage() -> dict[str, int]:
    async with get_session() as session:
        result = await session.execute(select(CommandUsage))
        return {row.command_name: row.usage_count for row in result.scalars().all()}


async def get_handler_results() -> list[HandlerResult]:
    async with get_session() as session:
        result = await session.execute(
            select(HandlerResultRecord).order_by(HandlerResultRecord.id.desc()).limit(MAX_HANDLER_RESULTS)
        )
        rows = result.scalars().all()
        return [
            HandlerResult(
                command_name=row.command_name,
                message=row.message,
                result=row.result or [],
                matcher=row.matcher,
            )
            for row in reversed(rows)
        ]


async def get_exceptions() -> list[ExceptionStatus]:
    async with get_session() as session:
        result = await session.execute(
            select(ExceptionRecord).order_by(ExceptionRecord.id.desc()).limit(MAX_EXCEPTIONS)
        )
        rows = result.scalars().all()
        return [
            ExceptionStatus(
                exception=row.exception,
                session=row.session,
                message=row.message,
                bot_id=row.bot_id,
                timestamp=int(row.timestamp.timestamp()),
            )
            for row in reversed(rows)
        ]


async def get_openai_history() -> list[OpenAIHistory]:
    async with get_session() as session:
        result = await session.execute(
            select(OpenAIHistoryRecord).order_by(OpenAIHistoryRecord.id.desc()).limit(MAX_OPENAI_HISTORY)
        )
        rows = result.scalars().all()
        return [
            OpenAIHistory(
                model=row.model,
                identify=row.identify,
                messages=row.messages or [],
            )
            for row in reversed(rows)
        ]


@get_driver().on_startup
async def _() -> None:
    for matcher in matchers.provider[1]:
        matcher.simple_run = simple_run


@run_preprocessor
async def _(matcher: Matcher, state: T_State) -> None:
    state["handler_results"] = []
    if isinstance(matcher, AlconnaMatcher):
        command_name = matcher.command().command
    elif matcher.type == "message":
        try:
            command_name = list(matcher.rule.checkers)[0].call.cmds[0][0]
        except Exception as _:
            return
    else:
        return
    async with get_session() as session:
        result = await session.execute(select(CommandUsage).where(CommandUsage.command_name == command_name))
        record = result.scalar_one_or_none()
        if record:
            record.usage_count += 1
        else:
            session.add(CommandUsage(command_name=command_name, usage_count=1))
        await session.commit()
    state["status_report_command_name"] = command_name
    state["original_simple_run_method"] = matcher.simple_run


@run_postprocessor
async def _(matcher: Matcher, state: T_State, event: Event) -> None:
    if "handler_results" not in state or "status_report_command_name" not in state:
        return
    try:
        message = str(event.get_message())
    except ValueError:
        message = ""
    async with get_session() as session:
        session.add(
            HandlerResultRecord(
                command_name=state.get("status_report_command_name", ""),
                message=message,
                result=state["handler_results"],
                matcher=str(matcher),
                timestamp=datetime.now(),
            )
        )
        await session.commit()
    matcher.simple_run = state["original_simple_run_method"]


def parse_traceback_lines(exc_lines: list[str]) -> list[dict[str, str]]:
    result = []
    for line in exc_lines:
        line = line.rstrip("\n")
        if not line:
            continue
        if line.startswith('  File "'):
            result.append({"type": "file", "content": line})
        elif line.startswith("    "):
            result.append({"type": "code", "content": line})
        elif line.startswith("Traceback") or line.startswith("During handling"):
            result.append({"type": "header", "content": line})
        elif ": " in line and not line.startswith(" "):
            result.append({"type": "error", "content": line})
        else:
            result.append({"type": "normal", "content": line})
    return result


def extract_error_info(exception: Exception) -> tuple[str, str]:
    error_type = type(exception).__name__
    error_message = str(exception)
    return error_type, error_message


@run_postprocessor
async def _(exception: Optional[Exception], state: T_State, event: Event) -> None:
    if exception is None or "status_report_command_name" not in state:
        return
    user_id = await get_main_account(event.get_user_id())
    exc_lines = traceback.format_exception(exception)
    error_type, final_message = extract_error_info(exception)
    traceback_lines = parse_traceback_lines(exc_lines)

    keys = await generate_render_keys(lang, user_id, ["title", "tip_label", "tip_content", "render_title"], "error.")

    image = await render_template(
        "error.html.jinja",
        keys["render_title"],
        user_id,
        {
            "error_type": error_type,
            "final_message": final_message,
            "traceback_lines": traceback_lines,
        },
        keys=keys,
    )
    await UniMessage().image(raw=image).send()


@run_postprocessor
async def _(event: Event, bot: Bot, exception: Optional[Exception]) -> None:
    global event_counter
    if exception is None:
        event_counter = event_counter[0] + 1, event_counter[1] + 1
        return
    event_counter = event_counter[0] + 1, event_counter[1]
    try:
        session_id = event.get_session_id()
        message = event.get_message()
    except ValueError:
        message = None
        session_id = None
    async with get_session() as session:
        session.add(
            ExceptionRecord(
                exception="".join(traceback.format_exception(exception)),
                session=session_id,
                message=str(message),
                bot_id=bot.self_id,
                timestamp=datetime.now(),
            )
        )
        await session.commit()


async def report_openai_history(messages: "Messages", identify: str, model: str) -> None:
    message_list = [message if isinstance(message, dict) else message.model_dump() for message in messages]
    async with get_session() as session:
        session.add(
            OpenAIHistoryRecord(
                model=model,
                identify=identify,
                messages=message_list,
                timestamp=datetime.now(),
            )
        )
        await session.commit()


@scheduler.scheduled_job("cron", hour=4, id="cleanup_status_report")
async def cleanup_old_records() -> None:
    async with get_session() as session:
        for model, max_count in [
            (HandlerResultRecord, MAX_HANDLER_RESULTS),
            (ExceptionRecord, MAX_EXCEPTIONS),
            (OpenAIHistoryRecord, MAX_OPENAI_HISTORY),
        ]:
            count_result = await session.execute(select(func.count()).select_from(model))
            total = count_result.scalar() or 0
            if total > max_count:
                subq = (
                    select(model.id)
                    .order_by(model.id.desc())
                    .offset(max_count)
                    .subquery()
                )
                await session.execute(delete(model).where(model.id.in_(select(subq.c.id))))
        await session.commit()


@app.get("/admin/status")
async def get_status_report(request: Request, token: str, salt: str) -> StatusReport:
    if token != hashlib.sha256(f"{config.status_report_password}+{salt}".encode()).hexdigest():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return StatusReport(
        bots=await bots_status(request),
        exceptions=await get_exceptions(),
        plugins=[plugin.name for plugin in get_loaded_plugins()],
        event_counter=EventCounter(
            success=event_counter[1],
            total=event_counter[0],
            failed=event_counter[0] - event_counter[1],
        ),
        openai=await get_openai_history(),
        command_usage=await get_command_usage(),
        handler_results=await get_handler_results(),
    )
