"""setu 图片缓存。

缓存由索引文件 ``cache.json`` 与同目录下的图片文件组成，索引中的每条记录都带有
``cached_at`` / ``used_at`` 时间戳：

- ``used_at is None``：可用图片，供 ``#setu`` 随机抽取；
- ``used_at`` 不为空：已经发放出去的图片（例如签到卡片头图），不会再被随机抽取，
  但会在 ``setu_cache_ttl`` 秒内保留，可通过 ``#setu-g <id>`` 取回原图与元数据，
  过期后连同图片文件一起清理。
"""

import asyncio
import json
import random
import time
import traceback
from pathlib import Path
from typing import Optional

import aiofiles
from nonebot import get_driver, logger
from nonebot.compat import type_validate_python
from nonebot_plugin_localstore import get_cache_dir
from pydantic import BaseModel, Field

from .config import config
from .image import get_new_image
from .models import ImageData
from .types import ImageWithData

cache_dir = get_cache_dir("nonebot_plugin_larksetu")
CACHE_FILE = cache_dir.joinpath("cache.json")
CACHE_VERSION = 2


def get_image_id(data: ImageData) -> str:
    """图片在缓存中的唯一 ID（同时用作缓存文件名）"""
    return f"{data.pid}_{data.p}"


def _get_image_file(data: ImageData) -> Path:
    return cache_dir.joinpath(f"{get_image_id(data)}.{data.ext}")


class CacheEntry(BaseModel):
    """缓存索引中的一条记录"""

    data: ImageData
    # 图片进入缓存的时间
    cached_at: float
    # 图片被发放给其他功能的时间；为空表示仍在可用池中
    used_at: Optional[float] = None

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def is_expired(self, now: float) -> bool:
        return self.used_at is not None and now - self.used_at > config.setu_cache_ttl


class CacheIndex(BaseModel):
    version: int = CACHE_VERSION
    entries: list[CacheEntry] = Field(default_factory=list)


# 索引读写的互斥锁：缓存索引的读-改-写必须串行，否则并发请求会互相覆盖
_lock = asyncio.Lock()
# 补缓存任务，保证同一时间只有一个任务在下载图片
_refill_task: Optional[asyncio.Task] = None
_refill_lock = asyncio.Lock()


async def _load_index() -> CacheIndex:
    if not CACHE_FILE.exists():
        return CacheIndex()
    try:
        async with aiofiles.open(CACHE_FILE, encoding="utf-8") as f:
            raw = json.loads(await f.read())
    except Exception:
        logger.warning(f"读取 setu 缓存索引失败: {traceback.format_exc()}")
        return CacheIndex()
    # 旧版本直接保存 ImageData 列表，没有时间戳也没有使用状态
    if isinstance(raw, list):
        return _migrate_legacy_index(raw)
    try:
        return type_validate_python(CacheIndex, raw)
    except Exception:
        logger.warning(f"解析 setu 缓存索引失败: {traceback.format_exc()}")
        return CacheIndex()


def _migrate_legacy_index(raw: list) -> CacheIndex:
    """把旧版本的 ImageData 列表转换为新的缓存索引"""
    now = time.time()
    entries: list[CacheEntry] = []
    for item in raw:
        try:
            entries.append(CacheEntry(data=type_validate_python(ImageData, item), cached_at=now))
        except Exception:
            logger.warning(f"跳过无法解析的旧版 setu 缓存记录: {traceback.format_exc()}")
    if entries:
        logger.info(f"已迁移 {len(entries)} 条旧版 setu 缓存记录")
    return CacheIndex(entries=entries)


async def _save_index(index: CacheIndex) -> None:
    async with aiofiles.open(CACHE_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps(index.model_dump(), ensure_ascii=False))


async def _write_image_file(data: ImageData, image: bytes) -> None:
    async with aiofiles.open(_get_image_file(data), "wb") as f:
        await f.write(image)


async def _read_image_file(data: ImageData) -> bytes:
    async with aiofiles.open(_get_image_file(data), "rb") as f:
        return await f.read()


def _delete_image_file(entry: CacheEntry) -> None:
    try:
        _get_image_file(entry.data).unlink(missing_ok=True)
    except Exception:
        logger.warning(f"删除 setu 缓存图片失败: {traceback.format_exc()}")


def _purge_expired(index: CacheIndex, now: float) -> list[CacheEntry]:
    """从索引中移除过期记录，返回被移除的记录（用于清理文件）"""
    expired = [entry for entry in index.entries if entry.is_expired(now)]
    for entry in expired:
        index.entries.remove(entry)
    return expired


def _trim_pool(index: CacheIndex) -> list[CacheEntry]:
    """可用池超过上限时淘汰最旧的记录，返回被移除的记录"""
    pool = [entry for entry in index.entries if not entry.is_used]
    evicted = pool[: max(len(pool) - config.setu_cache_count, 0)]
    for entry in evicted:
        index.entries.remove(entry)
    return evicted


def _drop_files(entries: list[CacheEntry]) -> None:
    for entry in entries:
        _delete_image_file(entry)


async def _store_entry(data: ImageData, image: bytes, *, retain: bool = False) -> None:
    """把图片写入缓存并登记到索引；retain 为 True 时直接标记为已使用"""
    await _write_image_file(data, image)
    now = time.time()
    async with _lock:
        index = await _load_index()
        expired = _purge_expired(index, now)
        if not any(get_image_id(entry.data) == get_image_id(data) for entry in index.entries):
            index.entries.append(CacheEntry(data=data, cached_at=now, used_at=now if retain else None))
        evicted = _trim_pool(index)
        await _save_index(index)
    _drop_files(expired + evicted)


async def _claim_entry(*, landscape_only: bool, retain: bool) -> Optional[CacheEntry]:
    """从可用池中取出一条记录

    retain 为 True 时标记为已使用（在 TTL 内保留，可再按 ID 取回），否则直接从索引中移除。
    调用方负责在读取完图片后清理文件。
    """
    async with _lock:
        index = await _load_index()
        now = time.time()
        expired = _purge_expired(index, now)
        pool = [
            entry
            for entry in index.entries
            if not entry.is_used and (not landscape_only or entry.data.width > entry.data.height)
        ]
        entry = random.choice(pool) if pool else None  # nosec B311
        if entry is not None:
            if retain:
                entry.used_at = now
            else:
                index.entries.remove(entry)
        await _save_index(index)
    _drop_files(expired)
    return entry


async def _remove_entry(entry: CacheEntry) -> None:
    async with _lock:
        index = await _load_index()
        for saved in list(index.entries):
            if get_image_id(saved.data) == get_image_id(entry.data):
                index.entries.remove(saved)
                await _save_index(index)
                break
    _delete_image_file(entry)


async def _read_entry(entry: CacheEntry, *, retain: bool) -> Optional[ImageWithData]:
    try:
        image = await _read_image_file(entry.data)
    except Exception:
        logger.error(f"读取 setu 缓存图片失败: {traceback.format_exc()}")
        await _remove_entry(entry)
        return None
    if not retain:
        # 随机抽取的图片不保留原图，避免缓存无限增长
        _delete_image_file(entry)
    return {"data": entry.data, "image": image}


async def _purge_expired_entries() -> None:
    async with _lock:
        index = await _load_index()
        expired = _purge_expired(index, time.time())
        if expired:
            await _save_index(index)
    _drop_files(expired)


async def _get_pool_size() -> int:
    async with _lock:
        index = await _load_index()
    return sum(1 for entry in index.entries if not entry.is_used)


async def _create_image_cache() -> bool:
    try:
        image = await get_new_image()
        await _store_entry(image["data"], image["image"])
        return True
    except Exception:
        logger.warning(f"更新 setu 缓存失败: {traceback.format_exc()}")
    return False


async def _fill_pool() -> None:
    """把可用池补满到 ``setu_cache_count``，同一时间只会有一个补缓存任务在跑"""
    if _refill_lock.locked():
        return
    async with _refill_lock:
        # 单次补缓存最多尝试的图片数，失败时留到下一次请求再补
        for _ in range(config.setu_cache_count * 2):
            await _purge_expired_entries()
            if await _get_pool_size() >= config.setu_cache_count:
                return
            if not await _create_image_cache():
                await asyncio.sleep(1)


def request_refill() -> None:
    """在后台补满缓存（已有任务在跑时直接返回）"""
    global _refill_task
    if _refill_task is not None and not _refill_task.done():
        return
    _refill_task = asyncio.create_task(_fill_pool())


@get_driver().on_startup
async def _() -> None:
    async def _startup_refill() -> None:
        logger.info("5s 后开始更新 setu 缓存")
        await asyncio.sleep(5)
        logger.info("开始更新 setu 缓存 ...")
        await _fill_pool()
        logger.success("setu 缓存更新完成！")

    asyncio.create_task(_startup_refill())


async def get_image() -> ImageWithData:
    """从缓存中随机取一张图片

    取出的图片不会再被随机抽取，也不会保留原图（避免缓存无限增长）。
    缓存为空或读取失败时直接下载一张新图片。
    """
    request_refill()
    entry = await _claim_entry(landscape_only=False, retain=False)
    if entry is not None and (result := await _read_entry(entry, retain=False)) is not None:
        return result
    return await get_new_image()


async def get_landscape_image() -> Optional[ImageWithData]:
    """取出一张横版图片，用于签到卡片头图

    取出的图片在 ``setu_cache_ttl`` 内保留，可再通过 :func:`get_cached_image` 按 ID 取回原图与元数据；
    缓存中没有横版图时直接补一张新图，横版就保留给调用方，否则放回缓存并返回 ``None``。
    """
    request_refill()
    entry = await _claim_entry(landscape_only=True, retain=True)
    if entry is not None:
        return await _read_entry(entry, retain=True)
    try:
        image = await get_new_image()
    except Exception:
        logger.warning(f"获取横版 setu 图片失败: {traceback.format_exc()}")
        return None
    if image["data"].width > image["data"].height:
        await _store_entry(image["data"], image["image"], retain=True)
        return image
    await _store_entry(image["data"], image["image"])
    return None


async def get_cached_image(image_id: str) -> Optional[ImageWithData]:
    """按 ID 取回仍在缓存中的图片及其元数据（``#setu-g``），已过期或不存在时返回 ``None``"""
    image_id = image_id.strip()
    if not image_id:
        return None
    async with _lock:
        index = await _load_index()
        expired = _purge_expired(index, time.time())
        entry = next((entry for entry in index.entries if get_image_id(entry.data) == image_id), None)
        if expired:
            await _save_index(index)
    _drop_files(expired)
    if entry is None:
        return None
    return await _read_entry(entry, retain=True)
