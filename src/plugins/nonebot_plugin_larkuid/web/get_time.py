import base64
from datetime import datetime
from typing import Optional, cast
from sqlalchemy.exc import NoResultFound
from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app

from ...nonebot_plugin_larkuser.utils.gsc_time import get_galactic_time
from ...nonebot_plugin_larkuser.utils.user import get_user
from ...nonebot_plugin_larkuser.utils.level import get_level_by_experience
from ..types import BasicUserResponse, DetailedUserResponse, TimeResponse
from ..session import get_user_data
from ...nonebot_plugin_larkuser.models import UserData


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
        "galactic": {
            "array": galactic_time,
            "strftime": "{}-{}-{}, {}:{}:{}".format(*galactic_time)
        }
    }