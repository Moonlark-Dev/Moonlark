from datetime import datetime
from typing import Literal

from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters import Event

from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import async_scoped_session

from .models import TimeProgressSubscription
from .utils import (
    calculate_percentage_of_day,
    calculate_percentage_of_month,
    calculate_percentage_of_year,
    generate_progress_bar,
    get_next_push_info,
)

alc = Alconna(
    "time-progress",
    Subcommand("sub", Args["action?", Literal["on", "off"], None]),
)
lang = LangHelper()
progress = on_alconna(alc)


@progress.assign("$main")
async def show_progress(user_id: str = get_user_id()) -> None:
    """显示时间进度"""
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


@progress.assign("sub")
async def handle_subscription(
    event: Event,
    action: Literal["on", "off"] | None,
    session: async_scoped_session,
    user_id: str = get_user_id(),
) -> None:
    """处理订阅命令"""
    if not isinstance(event, GroupMessageEvent):
        await lang.finish("sub.group_only", user_id)

    group_id = str(event.group_id)

    # 无参数时显示状态面板
    if action is None:
        subscription = await session.get(TimeProgressSubscription, {"group_id": group_id})
        enabled = subscription.enabled if subscription else False
        status_text = await lang.text("sub.status_on" if enabled else "sub.status_off", user_id)
        next_pct, next_time = get_next_push_info()

        await lang.finish(
            "sub.status",
            user_id,
            status_text,
            next_pct,
            next_time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    # 开启订阅
    if action == "on":
        subscription = await session.get(TimeProgressSubscription, {"group_id": group_id})
        if subscription:
            subscription.enabled = True
        else:
            subscription = TimeProgressSubscription(group_id=group_id, enabled=True)
            session.add(subscription)
        await session.commit()
        await lang.finish("sub.enabled", user_id)

    # 关闭订阅
    if action == "off":
        subscription = await session.get(TimeProgressSubscription, {"group_id": group_id})
        if subscription:
            subscription.enabled = False
            await session.commit()
        await lang.finish("sub.disabled", user_id)
