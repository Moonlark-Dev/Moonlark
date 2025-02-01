from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_render import render_template
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_sign import is_user_signed
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_bag.utils.color import color_common_item_list
from nonebot_plugin_bag.utils.give import give_item_by_list
from .utils import get_schedule_status, get_schedule_list, schedule_model_to_dict

matcher = on_alconna(Alconna("schedule", Subcommand("collect")))
lang = LangHelper()


@matcher.assign("collect")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    if not is_user_signed(user_id):
        await lang.finish("collect.need_sign", user_id)
    collected_tasks = 0
    for task_id, task in (await get_schedule_list()).items():
        result = await get_schedule_status(user_id, task_id, session)
        if result and result.completed_count >= task["completion_required"] and not result.collected:
            collected_tasks += 1
            result.collected = True
            await give_item_by_list(user_id, task["award"])
    await session.commit()
    await lang.finish("collecnt.done", user_id, collected_tasks)
            


@matcher.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    image = await render_template(
        "schedule.html.jinja",
        await lang.text("command.title", user_id),
        user_id,
        {
            "text": {
                "finished": await lang.text("command.finished", user_id),
                "collected": await lang.text("command.finished", user_id),
                "unfinished": await lang.text("command.unfinished", user_id),
                "award": await lang.text("command.award", user_id)
            },
            "schedule": [{
                "status": schedule_model_to_dict(await get_schedule_status(user_id, task_id, session)),
                "completed_count": task["completion_required"],
                "name": await lang.text(f"task_{task_id}.name", user_id),
                "description": await lang.text(f"task_{task_id}.description", user_id),
                "award_items": await color_common_item_list([await get_item(
                    get_location_by_id(item["item_id"]),
                    user_id,
                    item["count"],
                    item["data"]
                ) for item in task["award"]], user_id)
            } for task_id, task in (await get_schedule_list()).items()]
        }
    )

