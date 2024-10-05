from typing import Literal
from ...nonebot_plugin_larkutils import get_user_id
from nonebot.log import logger
from ..utils.tasks import get_finished_tasks, get_task_by_number, get_available_tasks
from ..__main__ import matcher
from ..lang import lang_define, lang


@matcher.assign("view")
async def _(view_number: int, user_id: str = get_user_id()) -> None:
    finished_tasks = await get_finished_tasks(user_id)
    try:
        task_id, task = await get_task_by_number(view_number)
    except ValueError:
        logger.waring(f"{traceback.format_exc()}")
        await lang.finish("start_command.not_found", user_id)
    await lang.finish(
        "view_command.info",
        user_id,
        view_number,
        await lang_define.text(f"{task_id.getPath()}.name", user_id),
        await lang_define.text(f"{task_id.getPath()}.description", user_id),
        str(task_id) in finished_tasks,
        any([str(id_) == str(task_id) for id_, _ in await get_available_tasks(finished_tasks)]),
        len(task.story),
        task.type,
    )
