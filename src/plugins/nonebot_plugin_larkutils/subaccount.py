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

import aiofiles
from nonebot_plugin_localstore import get_data_file
import json
from nonebot import get_driver

data_file = get_data_file("nonebot_plugin_larkutils", "subaccounts.json")


@get_driver().on_startup
async def _() -> None:
    async with aiofiles.open(data_file, "r+", encoding="utf-8") as f:
        try:
            json.loads(await f.read())
        except json.JSONDecoder:
            await f.truncate(0)
            await f.write("{}")


async def set_main_account(user_id: str, main_account: str) -> None:
    async with aiofiles.open(data_file, "r", encoding="utf-8") as f:
        data = json.loads(await f.read())
    data[user_id] = main_account
    async with aiofiles.open(data_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, indent=4, ensure_ascii=False))


async def get_main_account(user_id: str) -> str:
    async with aiofiles.open(data_file, "r", encoding="utf-8") as f:
        data = json.loads(await f.read())
        return data[user_id]
