import json
import time
from typing import Optional, cast
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from nonebot import get_app

app = cast(FastAPI, get_app())


@app.middleware("http")
async def add_timer_header(request: Request, call_next):
    start_time = time.time()
    response = cast(Response, await call_next(request))
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{round(process_time*1000, 1)} ms"
    return response
