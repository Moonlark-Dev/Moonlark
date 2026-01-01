from datetime import datetime

from nonebot_plugin_alconna import Alconna, on_alconna

from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils.user import get_user_id
from .utils import (
    calculate_percentage_of_day,
    calculate_percentage_of_month,
    calculate_percentage_of_year,
    generate_progress_bar,
)

alc = Alconna("time-progress")
lang = LangHelper()
progress = on_alconna(alc)


@progress.handle()
async def _(user_id: str = get_user_id()) -> None:
    time = datetime.now()
    year_pct = calculate_percentage_of_year()
    month_pct = calculate_percentage_of_month()
    day_pct = calculate_percentage_of_day()

    await lang.finish(
        "progress.progress",
        user_id,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        time.year,
        year_pct,
        generate_progress_bar(year_pct),
        time.month,
        month_pct,
        generate_progress_bar(month_pct),
        time.day,
        day_pct,
        generate_progress_bar(day_pct),
        reply_message=True,
        at_sender=False,
    )
