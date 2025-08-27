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
import json
import traceback
from datetime import datetime
from typing import cast, Optional, TYPE_CHECKING

import aiofiles
from fastapi import FastAPI
from nonebot import get_app, get_loaded_plugins, get_driver
from nonebot.message import run_postprocessor, run_preprocessor
from nonebot.params import T_State
from nonebot_plugin_alconna.matcher import AlconnaMatcher
from nonebot_plugin_bots.__main__ import bots_status
from nonebot_plugin_localstore import get_data_dir
from nonebot.adapters import Event, Bot
from nonebot.matcher import Matcher, matchers
from fastapi import Request, status
from fastapi.exceptions import HTTPException
from .config import config
from .types import ExceptionStatus, EventCounter, OpenAIHistory, StatusReport, HandlerResult

if TYPE_CHECKING:
    from nonebot_plugin_openai.types import Messages

data_dir = get_data_dir("nonebot_plugin_status_report")
app = cast(FastAPI, get_app())
event_counter = (0, 0)  # total, success

async def get_command_usage() -> dict[str, int]:
    if data_dir.joinpath("commands.json").is_file():
        async with aiofiles.open(data_dir.joinpath("commands.json"), "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    return {}

from .matcher import simple_run

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
    commands = await get_command_usage()
    commands[command_name] = commands.get(command_name, 0) + 1
    async with aiofiles.open(data_dir.joinpath("commands.json"), "w", encoding="utf-8") as f:
        await f.write(json.dumps(commands, ensure_ascii=False, indent=4))
    state["status_report_command_name"] = command_name
    state["original_simple_run_method"] = matcher.simple_run



async def get_handler_results() -> list[HandlerResult]:
    if data_dir.joinpath("handler.json").is_file():
        async with aiofiles.open(data_dir.joinpath("handler.json"), "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    return []


@run_postprocessor
async def _(matcher: Matcher, state: T_State, event: Event) -> None:
    if "handler_results" not in state or "status_report_command_name" not in state:
        return
    try:
        message = str(event.get_message())
    except ValueError:
        message = ""
    results = await get_handler_results()
    results.append(HandlerResult(
        message=message,
        command_name=state.get("status_report_command_name", ""),
        result=state["handler_results"],
        matcher=str(matcher)
    ))
    async with aiofiles.open(data_dir.joinpath("handler.json"), "w", encoding="utf-8") as f:
        await f.write(json.dumps(results[-20:], ensure_ascii=False, indent=4))
    matcher.simple_run = state["original_simple_run_method"]




@run_postprocessor
async def _(event: Event, bot: Bot, exception: Optional[Exception]) -> None:
    global event_counter
    if exception is None:
        event_counter = event_counter[0] + 1, event_counter[1] + 1
        return
    event_counter = event_counter[0] + 1, event_counter[1]
    exc_list = await get_exceptions()
    try:
        session_id = event.get_session_id()
        message = event.get_message()
    except ValueError:
        message = None
        session_id = None
    exc_list.append(
        ExceptionStatus(
            timestamp=int(datetime.now().timestamp()),
            bot_id=bot.self_id,
            message=str(message),
            session=session_id,
            exception="".join(traceback.format_exception(exception)),
        )
    )
    exc_list = exc_list[-20:]
    async with aiofiles.open(data_dir.joinpath("exceptions.json"), "w", encoding="utf-8") as f:
        await f.write(json.dumps(exc_list, ensure_ascii=False, indent=4))



async def report_openai_history(messages: "Messages", identify: str, model: str) -> None:
    message_list = [message if isinstance(message, dict) else message.model_dump() for message in messages]
    history = await get_openai_history()
    history.append(OpenAIHistory(model=model, identify=identify, messages=message_list))
    async with aiofiles.open(data_dir.joinpath("openai.json"), "w", encoding="utf-8") as f:
        await f.write(json.dumps(history[-20:], ensure_ascii=False, indent=4))


async def get_exceptions() -> list[ExceptionStatus]:
    if not data_dir.joinpath("exceptions.json").is_file():
        return []
    async with aiofiles.open(data_dir.joinpath("exceptions.json"), "r", encoding="utf-8") as f:
        return json.loads(await f.read())


async def get_openai_history() -> list[OpenAIHistory]:
    if not data_dir.joinpath("openai.json").is_file():
        return []
    async with aiofiles.open(data_dir.joinpath("openai.json"), "r", encoding="utf-8") as f:
        return json.loads(await f.read())


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
        handler_results=await get_handler_results()
    )
