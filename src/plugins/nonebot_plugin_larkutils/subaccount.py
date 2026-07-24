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

"""子账号与主账号映射管理模块."""

import aiofiles
from nonebot_plugin_localstore import get_data_dir

data_file = get_data_dir("nonebot_plugin_larkutils")


async def set_main_account(user_id: str, main_account: str) -> None:
    """设置用户的主账号."""
    async with aiofiles.open(data_file.joinpath(user_id), "w", encoding="utf-8") as f:
        await f.write(main_account)


async def get_main_account(user_id: str) -> str:
    """获取用户的主账号."""
    file = data_file.joinpath(user_id)
    if file.exists():
        async with aiofiles.open(file, "r", encoding="utf-8") as f:
            return (await f.read()) or user_id
    else:
        return user_id
