import asyncio
import time

from fastapi import Request
from nonebot import get_app

from ..config import config
from ..models import LoginRequest
from ..rate_limit import rate_limit
from ..session import InvalidSessionError, authenticate, create_session, get_rotated_session_id
from ..types import LoginPendingResponse, LoginResponse

PENDING_CHECK_INTERVAL = 1


@get_app().post("/api/login")
async def _(
    request: Request,
    data: LoginRequest,
    _: None = rate_limit(config.login_rate_limit_times, config.login_rate_limit_window_seconds),
) -> LoginResponse:
    session_id, activate_code = await create_session(data.user_id, request, data.retention_days)
    return {
        "session_id": session_id,
        "activate_code": activate_code,
        "effective_time": config.unused_session_remove_delay,
        "command_prefix": config.command_start[0],
    }


@get_app().get("/api/login/pending")
async def _(request: Request, wait: int = 0) -> LoginPendingResponse:
    """查询当前会话是否已完成登录激活。

    `wait`（秒）大于 0 时为长轮询：服务端挂起请求，激活后立即返回，
    或到达超时上限（`login_pending_max_wait`，最长不超过该值）返回 `{"activated": false}`。
    前端只需每 ~25s 发起一次请求即可获得毫秒级的激活感知，替代原先的每秒轮询。
    会话无效 / 已过期 / 标识不匹配时返回 401。

    响应携带 `session_id`：激活时后端会轮换会话 ID（防 fixation），
    前端无论何时收到 activated 都应采用响应中的 ID。

    轮换发生在 verify 侧且旧行会被删除，因此激活后的第一次轮询拿旧 ID 鉴权必然
    401：此时按 `previous_session_id` 找回新 ID 返回 activated，而不是把 401
    透传给前端（那会被当成「验证超时」）。
    """
    deadline = time.monotonic() + min(max(wait, 0), config.login_pending_max_wait)
    while True:
        try:
            context = await authenticate(request, allow_pending=True)
        except InvalidSessionError:
            rotated = await get_rotated_session_id(request)
            if rotated is not None:
                return {"activated": True, "session_id": rotated}
            raise
        if not context.pending or time.monotonic() >= deadline:
            return {"activated": not context.pending, "session_id": context.session_id}
        await asyncio.sleep(PENDING_CHECK_INTERVAL)
