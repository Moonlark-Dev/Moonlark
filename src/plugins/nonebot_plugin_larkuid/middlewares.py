import time
from typing import cast
from fastapi import FastAPI, Request, Response
from nonebot import get_app
from fastapi.middleware.cors import CORSMiddleware

from .config import config

app = cast(FastAPI, get_app())

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def patch_header(request: Request, call_next):
    start_time = time.time()
    response = cast(Response, await call_next(request))
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{round(process_time*1000, 1)} ms"
    response.headers["Access-Control-Allow-Origin"] = config.cors_allow_origins[0] if config.cors_allow_origins else "*"
    return response
