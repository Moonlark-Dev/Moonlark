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
# ##############################################################################

"""QQ 官方 Bot 群聊接口客户端。

``nonebot-adapter-qq`` 目前没有提供下面两个接口，这里按 QQ 开放平台文档直接实现：

- ``GET /v2/groups/{group_openid}/info``：获取群基本信息（30 QPM）；
- ``GET /v2/groups/{group_openid}/members``：获取群成员列表（60 QPM，每页最多 30 条，游标分页）。

两个接口都只对白名单机器人开放，没有权限时平台返回错误码 ``11253``。
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from nonebot import logger
from nonebot.adapters.qq import Bot as QQBot
from nonebot.drivers import Request, Response

from .types import QQGroupInfo, QQGroupMemberInfo

# 应用无接口访问权限（仅白名单机器人可用）
PERMISSION_DENIED_CODE = 11253

# 群基本信息：30 QPM，留出余量按 ~28 QPM 调用
GROUP_INFO_MIN_INTERVAL = 2.2
# 群成员列表：60 QPM，留出余量按 ~55 QPM 调用
GROUP_MEMBERS_MIN_INTERVAL = 1.1

# 群成员列表单页最多返回的成员数（平台固定值，仅用于日志说明）
MEMBERS_PAGE_SIZE = 30


class QQGroupAPIError(Exception):
    """QQ 群接口调用失败"""

    def __init__(self, message: str, *, code: Optional[int] = None, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class QQGroupPermissionError(QQGroupAPIError):
    """当前应用没有调用该接口的权限（错误码 11253）"""


class QQGroupRateLimitError(QQGroupAPIError):
    """触发了平台的接口频率限制（HTTP 429）"""


class _Throttle:
    """请求节流器：串行化同一类接口的调用，保证调用间隔不小于 ``min_interval``。"""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def __aenter__(self) -> "_Throttle":
        await self._lock.acquire()
        wait = self._last_call + self._min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        return self

    async def __aexit__(self, *_: object) -> None:
        self._last_call = time.monotonic()
        self._lock.release()


_info_throttle = _Throttle(GROUP_INFO_MIN_INTERVAL)
_members_throttle = _Throttle(GROUP_MEMBERS_MIN_INTERVAL)


def _parse_time(value: Any) -> Optional[datetime]:
    """把接口返回的 RFC3339 时间转换为不带时区的 UTC 时间。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        logger.debug(f"无法解析 QQ 群成员入群时间: {value!r}")
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _extract_error(response: Response) -> tuple[Optional[int], Optional[str]]:
    """从响应体中提取平台错误码与错误信息。"""
    if not response.content:
        return None, None
    try:
        body = json.loads(response.content)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(body, dict):
        return None, None
    code = body.get("code")
    message = body.get("message")
    return (int(code) if isinstance(code, int) else None), (str(message) if message else None)


def _raise_for_response(response: Response) -> dict[str, Any]:
    """检查响应，失败时抛出 :class:`QQGroupAPIError`，成功时返回响应体。"""
    code, message = _extract_error(response)
    if response.status_code == 429:
        raise QQGroupRateLimitError("QQ 群接口触发频率限制", code=code, status_code=429)
    if code == PERMISSION_DENIED_CODE:
        raise QQGroupPermissionError(
            f"应用没有该群接口的访问权限（11253）: {message or ''}".strip(),
            code=code,
            status_code=response.status_code,
        )
    if not 200 <= response.status_code < 300:
        raise QQGroupAPIError(
            f"QQ 群接口返回异常状态码 {response.status_code}: {message or response.content!r}",
            code=code,
            status_code=response.status_code,
        )
    if code is not None and code != 0:
        raise QQGroupAPIError(f"QQ 群接口返回错误码 {code}: {message or ''}".strip(), code=code)
    if not response.content:
        return {}
    try:
        return json.loads(response.content)
    except json.JSONDecodeError as e:
        raise QQGroupAPIError(f"QQ 群接口返回了无法解析的响应: {response.content[:200]!r}") from e


async def _request_json(
    bot: QQBot,
    path: tuple[str, ...],
    *,
    throttle: _Throttle,
    params: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """调用 QQ 群接口并返回 JSON 响应体。"""
    async with throttle:
        request = Request(
            "GET",
            bot.adapter.get_api_base().joinpath("v2", "groups", *path),
            params=params or {},
            timeout=30,
        )
        request.headers.update(await bot.get_authorization_header())
        try:
            response = await bot.adapter.request(request)
        except Exception as e:
            # 网络层异常统一转换为接口异常，调用方只需处理 QQGroupAPIError
            raise QQGroupAPIError(f"请求 QQ 群接口失败: {e}") from e
    return _raise_for_response(response)


async def fetch_group_info(bot: QQBot, group_openid: str) -> QQGroupInfo:
    """获取群基本信息（群名称、简介、成员人数）。"""
    data = await _request_json(
        bot,
        (group_openid, "info"),
        throttle=_info_throttle,
    )
    member_count = data.get("group_member_num")
    return QQGroupInfo(
        group_openid=str(data.get("group_openid") or group_openid),
        group_name=str(data.get("group_name") or ""),
        description=str(data.get("group_finger_memo") or ""),
        member_count=int(member_count) if isinstance(member_count, int) else 0,
    )


def parse_group_member(data: dict[str, Any]) -> QQGroupMemberInfo:
    """把接口返回的单个成员对象转换为 :class:`QQGroupMemberInfo`。"""
    role = str(data.get("member_role") or "member")
    return QQGroupMemberInfo(
        member_openid=str(data.get("member_openid") or ""),
        nickname=str(data.get("username") or ""),
        role=role if role in ("member", "admin", "owner") else "member",
        is_bot=bool(data.get("bot")),
        joined_at=_parse_time(data.get("joined_at")),
        union_openid=(str(data["union_openid"]) if data.get("union_openid") else None),
    )


async def fetch_group_members_page(
    bot: QQBot,
    group_openid: str,
    cursor: str = "",
) -> tuple[list[QQGroupMemberInfo], str]:
    """获取一页群成员列表，返回 ``(成员列表, 下一页游标)``。

    下一页游标为空串表示已经到末页。
    """
    data = await _request_json(
        bot,
        (group_openid, "members"),
        throttle=_members_throttle,
        params={"cursor": cursor},
    )
    members = [
        member for member in (parse_group_member(raw) for raw in data.get("members") or []) if member.member_openid
    ]
    return members, str(data.get("next_cursor") or "")


async def fetch_all_group_members(
    bot: QQBot,
    group_openid: str,
    *,
    max_members: int,
) -> list[QQGroupMemberInfo]:
    """翻页拉取全部群成员（受 ``max_members`` 限制，防止异常游标导致死循环）。"""
    members: list[QQGroupMemberInfo] = []
    cursor = ""
    seen_cursors = {""}
    while True:
        page, next_cursor = await fetch_group_members_page(bot, group_openid, cursor)
        members.extend(page)
        if not next_cursor or next_cursor in seen_cursors:
            break
        if len(members) >= max_members:
            logger.warning(
                f"[larkuser] 群 {group_openid} 成员数超过上限 {max_members}，停止继续拉取",
            )
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return members[:max_members]
