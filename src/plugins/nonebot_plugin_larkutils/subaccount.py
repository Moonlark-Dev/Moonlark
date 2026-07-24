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

import aiofiles
import asyncio

from nonebot import get_driver
from nonebot_plugin_localstore import get_data_dir
from nonebot_plugin_orm import get_session

from .models import MainAccountMapping

# 文件迁移锁，确保启动时的数据迁移只执行一次
_migration_lock = asyncio.Lock()
_migration_done = False

data_file = get_data_dir("nonebot_plugin_larkutils")


async def set_main_account(user_id: str, main_account: str) -> None:
    """设置子账号对应的主账号映射"""
    async with get_session() as session:
        mapping = await session.get(MainAccountMapping, {"user_id": user_id})
        if mapping is None:
            mapping = MainAccountMapping(user_id=user_id, main_account=main_account)
            session.add(mapping)
        else:
            mapping.main_account = main_account
        await session.commit()


async def get_main_account(user_id: str) -> str:
    """获取子账号对应的主账号 user_id，如果不存在则返回自身"""
    await _ensure_migrated()
    async with get_session() as session:
        mapping = await session.get(MainAccountMapping, {"user_id": user_id})
        if mapping is not None:
            return mapping.main_account
    return user_id


async def _migrate_from_files() -> None:
    """将旧的文件存储的主账号映射数据迁移到数据库"""
    global _migration_done
    async with _migration_lock:
        if _migration_done:
            return
        _migration_done = True

    if not data_file.exists():
        return

    migrated_count = 0
    for file_path in data_file.iterdir():
        if not file_path.is_file():
            continue
        user_id = file_path.name
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                main_account = (await f.read()).strip()
        except Exception:
            continue
        if not main_account:
            continue

        async with get_session() as session:
            existing = await session.get(MainAccountMapping, {"user_id": user_id})
            if existing is None:
                session.add(MainAccountMapping(user_id=user_id, main_account=main_account))
                await session.commit()
                migrated_count += 1

    if migrated_count > 0:
        pass  # log if needed later


async def _ensure_migrated() -> None:
    """确保文件到数据库的迁移已完成"""
    if not _migration_done:
        await _migrate_from_files()


@get_driver().on_startup
async def _() -> None:
    """在启动时自动迁移旧的文件数据到数据库"""
    await _migrate_from_files()
