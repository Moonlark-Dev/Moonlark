from fastapi import FastAPI, Request
from typing import cast
from nonebot import get_app

from ..config import config

app = cast(FastAPI, get_app())


@app.get("/api/prefix")
async def _(request: Request) -> dict:
    return {"prefix": config.command_start[0]}
