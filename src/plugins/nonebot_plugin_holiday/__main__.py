from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg

from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id
from ..nonebot_plugin_render.render import render_template

from nonebot_plugin_alconna import UniMessage

holiday = on_command("holiday")
lang = LangHelper()


@holiday.handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    total = 100
    remaining_total = 10
    statutory = 100
    remaining_statutory = 10
    next_date_month = 1
    next_date_day = 1
    next_date_days = 3
    next_name = "测试"
    await holiday.finish(
        await UniMessage()
        .image(
            raw=await render_template(
                "holiday.html.jinja", await lang.text("holiday.title", user_id), user_id, {
                    "remaining_title": await lang.text("holiday.remaining.title", user_id),
                    "total": await lang.text("holiday.remaining.total", user_id),
                    "div_total": await lang.text("holiday.remaining.div", user_id, remaining_total, total),
                    "percent_total": str(round(remaining_total / total * 100, 1)),
                    "statutory": await lang.text("holiday.remaining.statutory", user_id),
                    "div_statutory": await lang.text("holiday.remaining.div", user_id, remaining_statutory, statutory),
                    "percent_statutory": str(round(remaining_statutory / statutory * 100, 1)),
                    "next_title": await lang.text("holiday.next.title", user_id),
                    "date": await lang.text("holiday.next.date", user_id, next_date_month, next_date_day),
                    "name": next_name,
                    "days": await lang.text("holiday.next.days", user_id, next_date_days)
                }
            )
        )
        .export()
    )
