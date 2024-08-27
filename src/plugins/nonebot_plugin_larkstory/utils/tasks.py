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

import aiofiles
from nonebot_plugin_localstore import get_data_file
import json
from pathlib import Path
from ...nonebot_plugin_item.registry import ResourceLocation

async def get_finished_tasks(user_id: str) -> list[str]:
    file = get_data_file("nonebot-plugin-larkstory", f"{user_id}.json")
    try:
        async with aiofiles.open(file, encoding="utf-8") as f:
            return json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return []

async def append_finished_task(user_id: str, id_: ResourceLocation) -> None:
    finished_task = await get_finished_tasks(user_id)
    finished_task.append(str(id_))
    file = get_data_file("nonebot-plugin-larkstory", f"{user_id}.json")
    async with aiofiles.open(file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(finished_task))


def get_task_list() -> list[ResourceLocation]:
    l = []
    for namespace in Path(__file__).parent.parent.joinpath("tasks").iterdir():
        for file in namespace.iterdir():
             l.append(ResourceLocation(namespace.name, file.name[:-5]))
    return l



