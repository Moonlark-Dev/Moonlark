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

import json

from aiofiles import open as aio_open
from nonebot import require

require("nonebot_plugin_localstore")
from nonebot_plugin_localstore import get_data_file  # noqa: E402

from .types import UpdateAnnouncement  # noqa: E402

ANNOUNCEMENT_FILE = get_data_file("nonebot_plugin_updates", "announcement.json")


async def load_announcement() -> UpdateAnnouncement | None:
    """读取本地保存的最新更新公告；未发布过或文件损坏时返回 None"""
    if not ANNOUNCEMENT_FILE.exists():
        return None
    try:
        async with aio_open(ANNOUNCEMENT_FILE, encoding="utf-8") as f:
            data = json.loads(await f.read())
        return UpdateAnnouncement.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return None


async def save_announcement(announcement: UpdateAnnouncement) -> None:
    """保存更新公告到本地文件"""
    async with aio_open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
        await f.write(announcement.model_dump_json())


async def clear_announcement() -> None:
    """清除当前更新公告"""
    ANNOUNCEMENT_FILE.unlink(missing_ok=True)
