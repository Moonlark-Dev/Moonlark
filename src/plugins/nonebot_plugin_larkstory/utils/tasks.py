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
from nonebot.compat import type_validate_json
from nonebot_plugin_localstore import get_data_file
import json
from pathlib import Path
from ...nonebot_plugin_item.registry import ResourceLocation
from .models import Task
from nonebot.log import logger

async def get_finished_tasks(user_id: str) -> list[str]:
    file = get_data_file("nonebot-plugin-larkstory", f"{user_id}.json")
    try:
        async with aiofiles.open(file, encoding="utf-8") as f:
            return json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        logger.waring(f"{traceback.format_exc()}")
        return []


async def append_finished_task(user_id: str, id_: ResourceLocation) -> None:
    finished_task = await get_finished_tasks(user_id)
    finished_task.append(str(id_))
    file = get_data_file("nonebot-plugin-larkstory", f"{user_id}.json")
    async with aiofiles.open(file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(finished_task))


def get_task_list() -> list[ResourceLocation]:
    task_list = []
    for namespace in Path(__file__).parent.parent.joinpath("tasks").iterdir():
        for file in namespace.iterdir():
            task_list.append(ResourceLocation(namespace.name, file.name[:-5]))
    return task_list


async def get_task(id_: ResourceLocation) -> Task:
    path = Path(__file__).parent.parent.joinpath("tasks") / id_.getNamespace() / f"{id_.getPath()}.json"
    async with aiofiles.open(path, encoding="utf-8") as f:
        return type_validate_json(Task, await f.read())


def is_task_available(finished_tasks: list[str], task: Task) -> bool:
    for required_task in task.requires:
        if required_task not in finished_tasks:
            return False
    return True


async def get_available_tasks(finished_tasks: list[str]) -> list[tuple[ResourceLocation, Task]]:
    tasks = []
    for task_id in get_task_list():
        task = await get_task(task_id)
        if is_task_available(finished_tasks, task):
            tasks.append((task_id, task))
    return tasks


async def get_task_by_number(number: int) -> tuple[ResourceLocation, Task]:
    for task_id in get_task_list():
        task = await get_task(task_id)
        if task.number == number:
            return task_id, task
    raise ValueError("Task not found")
