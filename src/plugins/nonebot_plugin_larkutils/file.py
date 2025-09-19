#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
import inspect
from types import ModuleType
from typing import Any, TypeVar, Optional, Callable

from nonebot import get_plugin_by_module_name
from nonebot_plugin_localstore import get_config_file, get_cache_file, get_data_file
from enum import Enum
from pathlib import Path
import json
import asyncio
import aiofiles

GetFilePathFunc = Callable[[str, str], Path]
file_locks: dict[Path, asyncio.Lock] = {}
T = TypeVar("T")

class FileType(Enum):
    data: GetFilePathFunc = get_data_file
    cache: GetFilePathFunc = get_cache_file
    config: GetFilePathFunc = get_config_file



class FileManager:

    def __init__(self, path: Path, default: T) -> None:
        if path not in file_locks:
            file_locks[path] = asyncio.Lock()
        self.lock = file_locks[path]
        self.path = path
        self.data = default

    async def __aenter__(self) -> "FileManager":
        await self.lock.acquire()
        await self.setup_file()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.save_file()
        self.lock.release()

    async def setup_file(self) -> None:
        try:
            async with aiofiles.open(self.path, mode="r", encoding="utf-8") as f:
                self.data = json.loads(await f.read())
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    # 考虑使用临时文件+原子替换的方式，避免写入过程中断导致文件损坏
    async def save_file(self) -> None:
        temp_path = self.path.with_suffix('.tmp')
        try:
            async with aiofiles.open(temp_path, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps(self.data, indent=4, ensure_ascii=False))
            # 原子替换
            temp_path.replace(self.path)
        except:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()
            raise


def get_module_name(module: ModuleType | None) -> str | None:
    if module is None:
        return None
    if (plugin := get_plugin_by_module_name(module.__name__)) is None:
        return None
    return plugin.name


def open_file(file_name: str, file_type: FileType, default: T = {}, plugin_name: Optional[str] = None) -> FileManager:
    module = inspect.getmodule(inspect.stack()[1][0])
    plugin_name = plugin_name or get_module_name(module) or ""
    if not plugin_name:
        raise ValueError("plugin_name cannot be empty")
    return FileManager(file_type.value(plugin_name, file_name), default)



