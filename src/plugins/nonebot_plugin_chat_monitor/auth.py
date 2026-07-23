#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

"""认证辅助函数"""

import hashlib
from datetime import datetime, timezone

from fastapi import Request, status
from fastapi.exceptions import HTTPException

from .config import config


async def verify_admin(token: str, salt: str) -> None:
    """验证 admin token，与 status_report 使用相同的方式。"""
    expected = _compute_hash(config.status_report_password, salt)
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access token")


async def verify_admin_request(request: Request) -> None:
    """从请求中提取认证信息并验证。

    优先使用 ``Authorization: Bearer <hash>`` Header，
    降级到 query parameters ``token`` + ``salt``。
    """
    # 尝试 Bearer header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # Bearer token 格式：<hash>:<salt> 或 <hash>.<salt>
        bearer_value = auth_header[7:]
        if ":" in bearer_value:
            token, salt = bearer_value.split(":", 1)
        elif "." in bearer_value:
            token, salt = bearer_value.split(".", 1)
        else:
            # 尝试解析 JSON body
            raise HTTPException(status_code=400, detail="Invalid Bearer format, expected <hash>:<salt>")
        return await verify_admin(token, salt)

    # 降级到 query params
    token = request.query_params.get("token", "")
    salt = request.query_params.get("salt", "")
    if token and salt:
        return await verify_admin(token, salt)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Use Authorization: Bearer <hash>:<salt> or ?token=&salt=",
    )


def _compute_hash(password: str, salt: str) -> str:
    return hashlib.sha256(f"{password}+{salt}".encode()).hexdigest()


def compute_ws_token(password: str, salt: str) -> str:
    """计算 WebSocket 认证用的 token。"""
    return _compute_hash(password, salt)


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()
