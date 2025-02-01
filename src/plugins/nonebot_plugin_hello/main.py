import copy
import random
from nonebot import on_message, on_type
from nonebot.rule import to_me
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_user_id
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.adapters import Message, Event
from nonebot_plugin_schedule.utils import complete_schedule

lang = LangHelper()


from datetime import datetime
from typing import Literal, TypedDict


def get_current_time_segement_name() -> Literal["morning", "afternoon", "night", "midnight"]:
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        return "morning"
    elif 12 <= current_hour < 18:
        return "afternoon"
    elif 18 <= current_hour < 24 or current_hour <= 2:
        return "night"
    else:
        return "midnight"


class AtGreetingsData(TypedDict):
    updated_day: int
    morning: bool
    morning_count: int
    afternoon: bool
    afternoon_count: int
    night: bool
    night_count: int


class AtData(TypedDict):
    count: int
    greetings: AtGreetingsData


DEFAULT_AT_GREETINGS: AtGreetingsData = {
    "updated_day": 0,
    "morning": False,
    "morning_count": 0,
    "afternoon": False,
    "afternoon_count": 0,
    "night": False,
    "night_count": 0,
}


@on_message(rule=to_me(), block=False).handle()
async def _(event: Event, user_id: str = get_user_id()) -> None:
    if event.get_plaintext():
        return
    await complete_schedule(user_id, "at")
    user = await get_user(user_id)
    fav = user.get_fav()
    if fav < 0.007 or not user.is_registered():
        await lang.finish("at.unregistered", user_id)
    at_data: AtData = user.get_config_key("at_data", {"count": 0, "greetings": copy.deepcopy(DEFAULT_AT_GREETINGS)})
    if (day := datetime.now().day) != at_data["greetings"]["updated_day"]:
        at_data["greetings"] = copy.deepcopy(DEFAULT_AT_GREETINGS)
        at_data["greetings"]["updated_day"] = day
    time_segment_name = get_current_time_segement_name()
    if time_segment_name != "midnight":
        at_data["greetings"][f"{time_segment_name}_count"] += 1
    at_data["count"] += 1
    if fav <= 0.007:
        await lang.send("at.unregistered", user_id)
    elif time_segment_name == "midnight":
        await lang.send("at.special.midnight", user_id)
    elif (
        random.random() <= 0.05
        or at_data["greetings"][f"{time_segment_name}_count"] == 20
        and not at_data["greetings"][time_segment_name]
    ):
        await lang.send(f"at.special.{time_segment_name}", user_id)
        if not at_data["greetings"][time_segment_name]:
            at_data["greetings"][time_segment_name] = True
            await user.add_fav(0.0002)
    elif at_data["greetings"][f"{time_segment_name}_count"] >= 20 and random.random() <= 0.05:
        await lang.send("at.busy", user_id)
    else:
        await lang.send("at.normal", user_id)
    await user.set_config_key("at_data", at_data)


@on_type(PokeNotifyEvent, block=False).handle()
async def _(user_id: str = get_user_id()) -> None:
    pass
    # TODO 画个饼，防止以后没东西想写。
