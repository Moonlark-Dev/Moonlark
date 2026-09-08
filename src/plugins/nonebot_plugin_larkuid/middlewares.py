import time
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from nonebot import get_app
from starlette.middleware.base import RequestResponseEndpoint

from .config import config

app = cast("FastAPI", get_app())

# 鉴权通过 Authorization 请求头携带、不依赖 Cookie，无需 credentials；
# 「通配源 + credentials」的组合不符合 CORS 规范且会被浏览器拒绝。
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def patch_header(request: Request, call_next: RequestResponseEndpoint):
    start_time = time.time()
    response = cast("Response", await call_next(request))
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{round(process_time * 1000, 1)} ms"
    # API 响应不进任何缓存（用户数据接口含个人信息）。
    # CORS 响应头由上方 CORSMiddleware 按 Origin 统一处理，不再手工覆写。
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response
