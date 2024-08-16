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

from nonebot_plugin_localstore import get_cache_file
import aiofiles
import json
import time

file = get_cache_file("nonebot-plugin-join-message", f"groups.json")


async def load_data() -> dict:
    try:
        async with aiofiles.open(file, encoding="utf-8") as f:
            return json.loads(await f.read())
    except json.JSONDecodeError:
        return {}
    except FileNotFoundError:
        return {}


async def on_group_joined(bot_id: str, group_id: str) -> None:
    data = await load_data()
    data[group_id] = {"time": time.time(), "bot": bot_id}
    async with aiofiles.open(file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data))
