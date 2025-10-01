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

from typing import TypedDict, Literal
from typing_extensions import TypedDict as ExtensionTypedDict

from nonebot_plugin_larkcave.models import CaveData


class CheckPassedResult(TypedDict):
    passed: Literal[True]


class CheckFailedResult(TypedDict):
    passed: Literal[False]
    similar_cave: CaveData
    similarity: float


CheckResult = CheckFailedResult | CheckPassedResult


class CaveMessage(TypedDict):
    cave_id: int
    message_id: str


class Image(ExtensionTypedDict):
    id: float
    data: str
    name: str


class RandomCaveResponse(ExtensionTypedDict):
    id: int
    content: str
    author: str
    time: float
    images: list[Image]
