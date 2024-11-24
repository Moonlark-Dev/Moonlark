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

import httpx
from .config import config
from typing import TypedDict, Optional
import asyncio

class QuestionData(TypedDict):
    origin: str
    text: str
    length: int

async def request_question() -> Optional[QuestionData]:
    async with httpx.AsyncClient() as client:
        request = await client.get(config.manual_copy_api)
    if request.status_code == 200:
        data = request.json()
        return {
            "origin": data["from"],
            "text": data["hitokoto"],
            "length": data["length"]
        }

async def get_question() -> QuestionData:
    while (question := await request_question()) is None:
        await asyncio.sleep(1)
    return question



