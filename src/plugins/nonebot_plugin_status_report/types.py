#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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

from typing import Optional, Any, TypedDict, Literal

from typing_extensions import TypedDict

from nonebot_plugin_bots.types import BotStatus


class ExceptionStatus(TypedDict):
    exception: str
    session: Optional[str]
    message: Optional[str]
    bot_id: str
    timestamp: int


class EventCounter(TypedDict):
    total: int
    success: int
    failed: int


class OpenAIHistory(TypedDict):
    model: str
    identify: str
    messages: list[dict[str, Any]]


class HandlerInfo(TypedDict):
    lineno: int
    filename: str
    name: str
    plugin: str


class RunResult(TypedDict):
    result: Literal["success", "skipped", "failed"]
    message: str
    handler: HandlerInfo
    timestamp: int


class HandlerResult(TypedDict):
    command_name: str
    message: str
    result: list[RunResult]
    matcher: str


class StatusReport(TypedDict):
    bots: dict[str, BotStatus]
    exceptions: list[ExceptionStatus]
    plugins: list[str]
    event_counter: EventCounter
    openai: list[OpenAIHistory]
    command_usage: dict[str, int]
    handler_results: list[HandlerResult]
