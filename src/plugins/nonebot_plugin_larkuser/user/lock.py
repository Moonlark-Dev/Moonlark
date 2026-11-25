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
"""用户级异步写锁。

签到发币、商店扣币、roll 结算等操作都是「读取当前值 -> 计算 -> 写回」，当同一个用户
在多个响应器 / 后台任务里同时被修改时，两个协程会基于同一份过期快照计算，后写入的
结果覆盖先写入的，造成 VimCoin 等数值丢失更新。

这里给每个用户一把 ``asyncio.Lock``：写操作在锁内重新读取数据库中的最新值再修改，
同一用户的写入因此被串行化（同一进程内）。锁不可重入，持有锁的代码里不要再次对
同一用户加锁。锁按引用计数回收，用户量很大时也不会无限累积。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

_locks: dict[str, asyncio.Lock] = {}
# 当前正在使用（持有或等待）锁的协程数量，用于在空闲时回收锁对象
_users: dict[str, int] = {}


@asynccontextmanager
async def user_write_lock(user_id: str) -> AsyncGenerator[None, None]:
    """获取指定用户的写锁，退出上下文时释放。"""
    lock = _locks.get(user_id)
    if lock is None:
        # 单线程事件循环内 get 与 set 之间没有 await，不会重复创建
        lock = _locks[user_id] = asyncio.Lock()
    _users[user_id] = _users.get(user_id, 0) + 1
    try:
        async with lock:
            yield
    finally:
        remaining = _users[user_id] - 1
        if remaining > 0:
            _users[user_id] = remaining
        else:
            _users.pop(user_id, None)
            _locks.pop(user_id, None)
