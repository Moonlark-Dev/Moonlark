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

"""QQ 官方 Bot 群聊相关的数据类型。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class QQGroupMemberInfo:
    """一个群成员的信息"""

    member_openid: str
    nickname: str = ""
    role: str = "member"
    is_bot: bool = False
    joined_at: Optional[datetime] = None
    union_openid: Optional[str] = None


@dataclass(frozen=True)
class QQGroupInfo:
    """群基本信息（附带本地缓存的同步时间）"""

    group_openid: str
    group_name: str = ""
    description: str = ""
    member_count: int = 0
    info_updated_at: Optional[datetime] = None
    members_synced_at: Optional[datetime] = None
