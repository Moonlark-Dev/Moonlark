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
from datetime import datetime
from typing import TypedDict

import httpx
from nonebot_plugin_alconna import UniMessage
from nonebot import on_command
from nonebot_plugin_preview.preview import screenshot
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template, generate_render_keys

matcher = on_command("hsr-calendar", aliases={"hsrc"})
lang = LangHelper()


class EventDataDict(TypedDict):
    location: str
    summary: str
    time: datetime


class EventListDict(TypedDict):
    ongoing: list[EventDataDict]
    coming: list[EventDataDict]


def parse_ics(ics_content: str) -> dict[str, EventDataDict]:
    events = {}
    current_event = {}
    lines = ics_content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 处理多行值（续行以空格开头）
        while i + 1 < len(lines) and lines[i + 1].startswith((" ", "\t")):
            i += 1
            next_line = lines[i].strip()
            if next_line:
                # 移除行首的转义逗号（如果有）
                if next_line.startswith(","):
                    next_line = next_line[1:]
                line += next_line

        if line == "BEGIN:VEVENT":
            current_event = {}
        elif line == "END:VEVENT":
            if current_event.get("uid"):
                events[current_event["uid"]] = {
                    "location": current_event.get("location", ""),
                    "summary": current_event.get("summary", ""),
                    "time": current_event.get("dtstart"),
                }
            current_event = {}
        else:
            # 解析键值对（处理带参数的键）
            parts = line.split(":", 1)
            if len(parts) < 2:
                i += 1
                continue

            key_part, value = parts
            key = key_part.split(";")[0].lower()  # 取主键名

            # 处理转义字符
            value = value.replace("\\,", ",")

            if key == "dtstart":
                # 解析日期时间格式：20250521T060000
                try:
                    dt_str = value[-15:]  # 取后15位时间部分
                    dt_obj = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
                    current_event["dtstart"] = dt_obj
                except ValueError:
                    pass
            elif key in ("uid", "summary", "location"):
                current_event[key] = value

        i += 1

    return events


async def get_calendar() -> EventListDict:
    calendar: EventListDict = {"ongoing": [], "coming": []}
    async with httpx.AsyncClient() as client:
        request = await client.get(
            "https://raw.githubusercontent.com/Trrrrw/hoyo_calendar/refs/heads/main/ics/%E5%B4%A9%E5%9D%8F%EF%BC%9A%E6%98%9F%E7%A9%B9%E9%93%81%E9%81%93.ics"
        )
    event_list = parse_ics(request.text)
    dt = datetime.now()
    event_time = {}
    for event in event_list.values():
        if event["summary"].endswith("结束"):
            summary = event["summary"][:-2]
            if summary not in event_time:
                event_time[summary] = {"end_time": event["time"], "start_time": None, "location": event["location"]}
            else:
                event_time[summary]["end_time"] = event["time"]
        else:
            summary = event["summary"]
            if summary not in event_time:
                event_time[summary] = {"end_time": None, "start_time": event["time"], "location": event["location"]}
            else:
                event_time[summary]["start_time"] = event["time"]
    for summary, data in event_time.items():
        if data["start_time"] and (data["start_time"] - dt).total_seconds() >= 0:
            calendar["coming"].append({"time": data["start_time"], "summary": summary, "location": data["location"]})
        elif data["end_time"] and (data["end_time"] - dt).total_seconds() >= 0:
            calendar["ongoing"].append({"time": data["end_time"], "summary": summary, "location": data["location"]})
    return calendar


@matcher.handle()
async def _(user_id: str = get_user_id()) -> None:
    c = await get_calendar()
    dt = datetime.now()
    events = {
        "ongoing": [
            {
                "remain_days": int((event["time"] - dt).total_seconds() // 86400),
                "summary": event["summary"],
                "location": event["location"],
            }
            for event in c["ongoing"]
        ],
        "coming": [
            {
                "remain_days": (event["time"] - dt).total_seconds() // 86400,
                "summary": event["summary"],
                "location": event["location"],
            }
            for event in c["coming"]
        ],
    }
    await UniMessage().image(
        raw=await render_template(
            "hkrpg_calendar.html.jinja",
            await lang.text("title", user_id),
            user_id,
            {"events": events},
            await generate_render_keys(
                lang, user_id, [f"template.{k}" for k in ["ongoing", "remain", "day", "coming", "coming_day"]]
            ),
        )
    ).send()
    await matcher.finish()
