#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

import math


def get_exchangeable_paw_coin_count(points: int, exchanged: int) -> int:
    """
    获取可兑换的 PawCoin 数量
    :param points: 积分总数
    :param exchanged: 已兑换的积分数量
    :return: 可兑换的 PawCoin 数量
    """
    return int(math.sqrt(points * 0.75)) - exchanged
