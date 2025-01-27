from datetime import datetime
from typing import cast
from fastapi import FastAPI, Request
from nonebot import get_app

from nonebot_plugin_larkutils.gsc_time import get_galactic_time
from ..types import TimeResponse

app = cast(FastAPI, get_app())


@app.get("/api/time")
async def _(request: Request) -> TimeResponse:
    now = datetime.now()
    galactic_time = get_galactic_time(now.timestamp())
    return {
        "earth": {
            "strftime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": now.timestamp(),
        },
        "galactic": {"array": galactic_time, "strftime": "{}-{}-{}, {}:{}:{}".format(*galactic_time)},
    }
