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

from ...nonebot_plugin_larkutils import get_user_id, is_private_message
from ..__main__ import matcher
from ..lang import lang, lang_define
from ..utils import get_task_by_number, is_task_available, get_finished_tasks, TaskExecutor, BreakError, append_finished_task


@matcher.assign("start")
async def _(start_number: int, user_id: str = get_user_id(), private: bool = is_private_message()) -> None:
    if not private:
        await lang.finish("start_command.not_private", user_id)
    try:
        task_id, task = await get_task_by_number(start_number)
    except ValueError:
        await lang.finish("start_command.not_found", user_id)
        return
    if not is_task_available(finished_tasks := await get_finished_tasks(user_id), task):
        await lang.finish("start_command.not_available", user_id)
    if str(task_id) in finished_tasks:
        await lang.finish("start_command.finished", user_id)
    name = await lang_define.text(f"{task_id.getPath()}.name", user_id)
    description = await lang_define.text(f"{task_id.getPath()}.description", user_id)
    await lang.send("start_command.start", user_id, name, description)
    executor = TaskExecutor(task_id.getPath(), task, user_id)
    try:
        await executor.execute()
    except BreakError as e:
        # 跳丢了
        await lang.finish("start_command.break", user_id, e.index)
    await append_finished_task(user_id, task_id)
    await lang.finish("start_command.finish", user_id)

