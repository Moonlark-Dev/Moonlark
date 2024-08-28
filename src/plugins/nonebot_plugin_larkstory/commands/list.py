from typing import Literal
from ...nonebot_plugin_larkutils import get_user_id

from ..utils.tasks import get_available_tasks, get_finished_tasks, get_task_list, get_task
from ..__main__ import matcher
from ..lang import lang_define, lang


@matcher.assign("list")
async def _(task_type: Literal["available", "all", "finished"], user_id: str = get_user_id()) -> None:
    finished_tasks = await get_finished_tasks(user_id)
    if task_type == "available":
        tasks = [i for i in await get_available_tasks(finished_tasks) if str(i[0]) not in finished_tasks]
    elif task_type == "all":
        tasks = [(id_, await get_task(id_)) for id_ in get_task_list()]
    else:
        tasks = [(id_, await get_task(id_)) for id_ in get_task_list() if str(id_) in finished_tasks]
    await lang.finish(
        "list_command.title",
        user_id,
        "\n".join(
            [
                await lang.text(
                    "list_command.item",
                    user_id,
                    task.number,
                    await lang_define.text(f"{task_id.getPath()}.name", user_id),
                )
                for task_id, task in tasks
            ]
        ),
    )
