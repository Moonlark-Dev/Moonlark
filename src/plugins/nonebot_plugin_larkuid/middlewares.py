import json
import time
from typing import Optional, cast
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from nonebot import get_app
from fastapi.middleware.cors import CORSMiddleware

app = cast(FastAPI, get_app())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的来源列表
    allow_credentials=True,  # 是否允许发送凭据
    allow_methods=["*"],  # 允许的请求方法
    allow_headers=["*"],  # 允许的请求头
)


@app.middleware("http")
async def patch_header(request: Request, call_next):
    start_time = time.time()
    response = cast(Response, await call_next(request))
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{round(process_time*1000, 1)} ms"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
