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

from .models import MenuPanelSettings  # noqa: E402

SETTINGS_FILE = get_data_file("nonebot_plugin_menupanel", "settings.json")


async def load_settings() -> MenuPanelSettings:
    """读取本地保存的菜单/面板配置"""
    if not SETTINGS_FILE.exists():
        return MenuPanelSettings()
    try:
        async with aio_open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.loads(await f.read())
        return MenuPanelSettings.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return MenuPanelSettings()


async def save_settings(settings: MenuPanelSettings) -> None:
    """保存菜单/面板配置到本地文件"""
    async with aio_open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        await f.write(settings.model_dump_json())
