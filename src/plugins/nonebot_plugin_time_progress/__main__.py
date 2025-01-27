from datetime import datetime
from typing import Literal

from nonebot_plugin_alconna import Alconna, Args, on_alconna

from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils.user import get_user_id
from .utils import calculate_percentage_of_day, calculate_percentage_of_month, calculate_percentage_of_year

alc = Alconna("time-progress")
lang = LangHelper()
progress = on_alconna(alc)


@progress.handle()
async def _(user_id: str = get_user_id()) -> None:
    time = datetime.now()
    await lang.finish(
        "progress.progress",
        user_id,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        time.year,
        calculate_percentage_of_year(),
        time.month,
        calculate_percentage_of_month(),
        time.day,
        calculate_percentage_of_day(),
        reply_message=True,
        at_sender=False,
    )
