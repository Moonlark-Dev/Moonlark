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

"""QQ 官方 Bot 群聊信息与群成员缓存。

QQ 开放平台提供的群信息接口（``/v2/groups/{group_openid}/info``）与群成员列表
接口（``/v2/groups/{group_openid}/members``）都只对白名单机器人开放，群成员列表
还有分页与频率限制，所以这里统一维护一份数据库缓存，并对外提供只读查询接口。
"""

# 导入 sync 以注册群消息监听与周期性同步任务
from . import sync as sync
from .cache import (
    NICK_SOURCE_GROUP_MEMBER,
    NICK_SOURCE_KEY,
    ensure_group_known,
    ensure_group_members,
    fill_user_nicknames,
    get_cached_group_members,
    get_group_member,
    get_group_member_ids,
    get_group_member_nickname_map,
    get_group_name,
    get_group_record,
    get_qq_bot,
    refresh_group_info,
    refresh_group_members,
    remember_group,
    request_group_sync,
    sync_all_groups,
)
from .client import (
    QQGroupAPIError,
    QQGroupPermissionError,
    QQGroupRateLimitError,
    fetch_all_group_members,
    fetch_group_info,
    fetch_group_members_page,
)
from .types import QQGroupInfo, QQGroupMemberInfo

__all__ = [
    "NICK_SOURCE_GROUP_MEMBER",
    "NICK_SOURCE_KEY",
    "QQGroupAPIError",
    "QQGroupInfo",
    "QQGroupMemberInfo",
    "QQGroupPermissionError",
    "QQGroupRateLimitError",
    "ensure_group_known",
    "ensure_group_members",
    "fetch_all_group_members",
    "fetch_group_info",
    "fetch_group_members_page",
    "fill_user_nicknames",
    "get_cached_group_members",
    "get_group_member",
    "get_group_member_ids",
    "get_group_member_nickname_map",
    "get_group_name",
    "get_group_record",
    "get_qq_bot",
    "refresh_group_info",
    "refresh_group_members",
    "remember_group",
    "request_group_sync",
    "sync",
    "sync_all_groups",
]
