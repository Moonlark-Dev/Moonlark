from ...nonebot_plugin_larkutils import get_user_id

from ..utils.tasks import get_available_tasks, get_finished_tasks
from ..__main__ import matcher
from ..lang import lang


@matcher.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    finished_tasks = await get_finished_tasks(user_id)
    available = await get_available_tasks(finished_tasks)
    await lang.reply("main_command.info", user_id, len(finished_tasks), len(available))

