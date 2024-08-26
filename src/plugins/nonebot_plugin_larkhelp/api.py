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

from nonebot import get_app
from typing import cast
from fastapi import FastAPI, HTTPException, status

from ..nonebot_plugin_larkuid.session import get_user_id
from .__main__ import lang, get_help_list, get_help_dict

app = cast(FastAPI, get_app())


@app.get("/api/help/commands")
async def _() -> list[str]:
    return list(get_help_list().keys())


@app.get("/api/help/commands/{name}")
async def _(name: str, user_id: str = get_user_id("-1")) -> dict[str, str | list[str]]:
    try:
        return await get_help_dict(name, user_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
