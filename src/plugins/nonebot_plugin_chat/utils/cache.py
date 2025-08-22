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

import asyncio
import time
from typing import Any, Optional


class AsyncCache:
    def __init__(self, expiration_time: int = 60):
        """
        初始化缓存管理系统
        :param expiration_time: 缓存项的默认过期时间（秒）
        """
        self.cache = {}  # 存储缓存数据的字典
        self.expiration_time = expiration_time  # 缓存过期时间
        self.lock = asyncio.Lock()  # 异步锁，确保缓存操作的原子性
        # 启动异步任务来定期清理过期缓存
        asyncio.create_task(self.cleanup())

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存项，支持自动过期
        :param key: 缓存的键
        :param value: 缓存的值
        :param ttl: 缓存项的过期时间，默认为 None 使用默认的过期时间
        """
        ttl = ttl if ttl is not None else self.expiration_time
        expiration = time.time() + ttl  # 计算过期时间
        async with self.lock:
            self.cache[key] = {
                "value": value,
                "expiration": expiration
            }

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存项的值
        :param key: 缓存的键
        :return: 缓存的值，若不存在或已过期返回 None
        """
        async with self.lock:
            cache_item = self.cache.get(key)
            if cache_item:
                # 检查是否过期
                if time.time() < cache_item["expiration"]:
                    return cache_item["value"]
                else:
                    # 缓存过期，删除该项
                    del self.cache[key]
            return None

    async def delete(self, key: str):
        """
        删除缓存项
        :param key: 缓存的键
        """
        async with self.lock:
            if key in self.cache:
                del self.cache[key]

    async def cleanup(self):
        """
        定期清理过期的缓存项
        """
        while True:
            await asyncio.sleep(30)  # 每30秒执行一次清理操作
            async with self.lock:
                # 当前时间
                current_time = time.time()
                # 清理所有过期的缓存项
                keys_to_delete = [key for key, item in self.cache.items() if item["expiration"] < current_time]
                for key in keys_to_delete:
                    del self.cache[key]
