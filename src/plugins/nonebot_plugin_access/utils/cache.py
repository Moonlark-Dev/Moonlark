"""权限表的内存缓存。

权限检查由 run_preprocessor 对每条消息的每个 matcher 各执行一次，每次都查数据库
开销较大。这里把整张权限表缓存在内存中：启动时（on_startup）拉取一次，之后每
5 分钟刷新一次，权限表写入（utils/set_access.py）后也立即刷新。

缓存未加载时按需加载；缓存中没有记录的权限项沿用原来的默认值语义（默认放行）。
"""

from __future__ import annotations

import asyncio

from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import SubjectData

# subject -> name -> available
AccessTable = dict[str, dict[str, bool]]


class AccessCache:
    """内存中的权限表。

    读取直接访问当前表对象（刷新时整体替换，读取方不会看到刷新到一半的表），
    刷新由 asyncio.Lock 串行化，避免多个刷新同时读写数据库。
    """

    def __init__(self) -> None:
        self._table: AccessTable = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def loaded(self) -> bool:
        return self._loaded

    def get(self, subject: str, name: str, default: bool = True) -> bool:
        """读取缓存中的权限，缓存中没有该记录时返回 default。"""
        return self._table.get(subject, {}).get(name, default)

    def permissions_of(self, subject: str) -> dict[str, bool]:
        """读取某个主体的全部权限（web 接口用）。"""
        return dict(self._table.get(subject, {}))

    async def reload(self) -> int:
        """从数据库重新拉取整张权限表，返回读取到的记录数。"""
        async with self._lock:
            async with get_session() as session:
                rows = (
                    await session.execute(select(SubjectData.subject, SubjectData.name, SubjectData.available))
                ).all()
            table: AccessTable = {}
            for subject, name, available in rows:
                # 同一 (subject, name) 可能有多条记录，与原先 is_available 的 all() 语义保持一致
                permissions = table.setdefault(subject, {})
                permissions[name] = permissions.get(name, True) and bool(available)
            self._table = table
            self._loaded = True
            logger.debug(f"权限表已刷新：{len(rows)} 条记录，{len(table)} 个主体")
            return len(rows)

    async def ensure_loaded(self) -> None:
        """缓存尚未加载时按需加载（启动钩子未执行时的兜底）。"""
        if not self._loaded:
            await self.reload()


access_cache = AccessCache()
