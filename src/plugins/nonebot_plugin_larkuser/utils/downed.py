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

from datetime import timedelta
from enum import Enum

from ..lang import lang
from ..models import UserData
from ..user.base import MoonlarkUser

RESCUE_COST = 50


def format_duration(delta: timedelta) -> str:
    """将时长格式化为人类可读文本"""
    total = int(max(0, delta.total_seconds()))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分钟"
    if minutes:
        return f"{minutes}分钟{seconds}秒" if seconds else f"{minutes}分钟"
    return f"{seconds}秒"


async def send_down_prompt(user_id: str, remaining: timedelta) -> None:
    """发送独立的倒地提示"""
    await lang.send("downed.prompt", user_id, format_duration(remaining))


class RescueResult(Enum):
    """救起操作的结果"""

    NOT_DOWNED = "not_downed"
    INSUFFICIENT_VIMCOIN = "insufficient"
    TARGET_INSUFFICIENT_VIMCOIN = "target_insufficient"
    SUCCESS = "success"


async def process_rescue(rescuer: MoonlarkUser, downed_user: MoonlarkUser, pay_by_rescuer: bool) -> RescueResult:
    """救起倒地用户的通用逻辑。

    :param rescuer: 发起救起的用户（需以 ``get_user(..., writable=True)`` 获取）
    :param downed_user: 被救起的倒地用户（同上，救起会写回 HP）
    :param pay_by_rescuer: True 时费用从救人者账户扣除，False 时从被救者账户扣除
    :return: 救起结果
    """
    if not await downed_user.is_down():
        return RescueResult.NOT_DOWNED
    payer = rescuer if pay_by_rescuer else downed_user

    def _pay(row: UserData) -> bool:
        # 余额判断与扣费必须在同一次加锁的修改里完成，否则等待确认期间余额可能被
        # 其它指令花掉，出现「检查通过、扣费失败，却仍然把人救起」的白嫖路径。
        balance = row.vimcoin or 0.0
        if balance < RESCUE_COST:
            return False
        row.vimcoin = balance - RESCUE_COST
        return True

    if not await payer.update(_pay):
        if pay_by_rescuer:
            return RescueResult.INSUFFICIENT_VIMCOIN
        return RescueResult.TARGET_INSUFFICIENT_VIMCOIN
    await downed_user.revive()
    return RescueResult.SUCCESS
