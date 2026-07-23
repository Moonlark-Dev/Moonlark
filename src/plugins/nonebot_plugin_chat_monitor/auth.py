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

from fastapi import status
from fastapi.exceptions import HTTPException

from .config import config


async def verify_admin(token: str, salt: str) -> None:
    """验证 admin token，与 status_report 使用相同的方式。"""
    expected = hashlib.sha256(
        f"{config.status_report_password}+{salt}".encode()
    ).hexdigest()
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access token"
        )


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()
