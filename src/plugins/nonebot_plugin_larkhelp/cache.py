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
"""LarkHelp 帮助面板独立磁盘缓存与热门指令榜单定时刷新。

为什么独立于 ``nonebot_plugin_render.cache``：
- 帮助面板由 Pillow 直接绘制，版式固定，不随 ``.theme``（default / simple / redpacket / wide）变化；
  若挂在 Render 的 ``@creator`` 上，会按 ``语言 × 主题`` 在 Render 缓存目录额外生成 12 份重复且无人读取的文件。
- 帮助面板顶部带有「热门指令」榜单与「数据更新于 YYYY-MM-DD」副标题，需要随统计数据周期性后台刷新，
  而不是仅在进程启动时静态生成一次。

因此本模块在 ``localstore`` 的 ``nonebot-plugin-larkhelp`` 缓存目录下仅按语言维护面板缓存（如 3 个语言共 3 份），
启动 ready 阶段先清理旧文件并在后台预热，运行期由 APScheduler 定时检查热门指令榜单与日期变化并原子替换缓存文件。
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
import hashlib
import os
import re
from typing import TYPE_CHECKING, Optional
import uuid

import aiofiles
from nonebot import get_driver
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larklang.__main__ import get_languages
from nonebot_plugin_localstore import get_cache_dir

from . import panel as help_panel
from .__main__ import get_help_list
from .config import config

if TYPE_CHECKING:
    from pathlib import Path

cache_dir: Path = get_cache_dir("nonebot-plugin-larkhelp")
_SAFE_LANG_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_refresh_lock = asyncio.Lock()
_last_signature: Optional[tuple[str, str]] = None


def get_cache_path(lang: str) -> Path:
    """获取指定语言的面板缓存文件路径（按语言唯一，不乘以主题）。"""
    if _SAFE_LANG_RE.fullmatch(lang):
        filename = f"panel_{lang}.webp"
    else:
        digest = hashlib.sha256(f"larkhelp::panel::{lang}".encode()).hexdigest()
        filename = f"panel_{digest}.webp"
    return cache_dir.joinpath(filename)


def has_cache_file(lang: str) -> bool:
    """判断指定语言的磁盘缓存文件是否存在。"""
    return get_cache_path(lang).is_file()


def clear_cache() -> None:
    """清空缓存目录下的旧面板文件并重置签名状态。"""
    global _last_signature
    _last_signature = None
    if not cache_dir.exists():
        return
    for file in cache_dir.iterdir():
        if file.is_file():
            file.unlink()


def _prepare_write_paths(lang: str) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = get_cache_path(lang)
    tmp_path = cache_dir.joinpath(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    return target, tmp_path


def _commit_tmp_file(tmp_path: Path, target: Path) -> None:
    tmp_path.replace(target)


def _remove_tmp_file(tmp_path: Path) -> None:
    if tmp_path.exists():
        with contextlib.suppress(OSError):
            tmp_path.unlink()


async def get_cache(lang: str) -> Optional[bytes]:
    """读取指定语言的帮助面板磁盘缓存；不存在或为空时返回 None。"""
    if not has_cache_file(lang):
        return None
    path = get_cache_path(lang)
    try:
        async with aiofiles.open(path, "rb") as f:
            data = await f.read()
    except OSError:
        logger.opt(exception=True).warning(f"读取 LarkHelp 面板缓存失败: {path}")
        return None
    else:
        return data or None


async def set_cache(lang: str, data: bytes) -> None:
    """原子写入指定语言的帮助面板磁盘缓存，避免并发读取到半写入文件。"""
    if not data:
        return
    target, tmp_path = _prepare_write_paths(lang)
    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(data)
        _commit_tmp_file(tmp_path, target)
    except Exception:
        _remove_tmp_file(tmp_path)
        raise


def _current_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def build_hot_signature(hot: list[tuple[str, int]]) -> str:
    return "|".join(f"{name}:{count}" for name, count in hot)


def filter_hot_for_help_list(hot_raw: list[tuple[str, int]], help_list: dict) -> list[tuple[str, int]]:
    """过滤出仍在非 superuser 帮助列表中的前三名热门指令（与面板去重规则一致）。"""
    valid_names = {name for name, item in help_list.items() if item.category != "superuser"}
    return [(name, count) for name, count in hot_raw if name in valid_names][:3]


async def _render_and_store_lang(
    lang: str,
    help_list: dict,
    hot: list[tuple[str, int]],
    today: str,
) -> bool:
    """渲染单个语言的帮助面板并写入磁盘缓存，成功返回 True。"""
    try:
        image = await help_panel.render_help_panel(
            f"mlsid::--lang={lang};--ignore-cache=y",
            help_list,
            ignore_cache=True,
            hot_override=hot,
            date_override=today,
        )
    except Exception:
        logger.opt(exception=True).warning(f"LarkHelp 帮助面板缓存渲染失败，跳过 {lang=}")
        return False
    if not image:
        logger.warning(f"LarkHelp 帮助面板缓存渲染返回空数据，跳过 {lang=}")
        return False
    try:
        await set_cache(lang, image)
    except Exception:
        logger.opt(exception=True).warning(f"LarkHelp 帮助面板缓存写入失败，跳过 {lang=}")
        return False
    return True


async def refresh_cache(*, force: bool = False) -> int:
    """后台刷新全部语言的帮助面板磁盘缓存。

    ``force=False`` 时会先比对当前日期与近 7 天热门指令前三名签名：若与上次成功刷新一致且
    各语言的磁盘缓存均在位，则直接跳过重绘，避免空闲时段无意义消耗 CPU。
    """
    global _last_signature
    async with _refresh_lock:
        help_list = get_help_list()
        if not help_list or not help_panel.font_available():
            return 0

        languages = list(get_languages().keys())
        if not languages:
            return 0

        today = _current_date()
        hot = filter_hot_for_help_list(await help_panel.get_hot_commands(), help_list)
        signature = (today, build_hot_signature(hot))
        if not force and _last_signature == signature and all(has_cache_file(lang) for lang in languages):
            logger.debug("LarkHelp 帮助面板热门指令榜单与日期未变化，跳过缓存重绘")
            return 0

        created = 0
        for lang in languages:
            if await _render_and_store_lang(lang, help_list, hot, today):
                created += 1
                logger.debug(f"成功更新 LarkHelp 帮助面板缓存：{lang=} ({signature[1] or '无热门数据'})")

        if created == len(languages):
            _last_signature = signature
        logger.success(f"LarkHelp 帮助面板缓存更新完成，共 {created} 个！")
        return created


async def warm_up_cache() -> None:
    """启动阶段后台预热入口：异常只记日志，不阻塞或中断机器人运行。"""
    try:
        await refresh_cache(force=True)
    except Exception:
        logger.opt(exception=True).warning("LarkHelp 帮助面板缓存预热失败，后续渲染将回退到按需渲染")


def start_cache_warm_up() -> None:
    """将启动预热放入 lifespan 任务组后台执行，不阻塞启动。"""
    logger.info("正在后台创建 LarkHelp 帮助面板缓存...")
    get_driver().task_group.start_soon(warm_up_cache)


@get_driver()._lifespan.on_ready  # ruff: ignore[private-member-access]
async def prepare_cache() -> None:
    """启动 ready 阶段清理旧缓存并在后台按语言预热。

    必须在 ready 阶段（所有插件的 ``on_startup`` 执行完之后）运行：
    此时 ``larkhelp.setup_help_list``、``larklang.load_languages`` 以及
    ``command_stats.register_help_hot_provider`` 均已完成初始化。
    """
    clear_cache()
    if not config.larkhelp_cache:
        logger.info("LarkHelp 帮助面板缓存已关闭（LARKHELP_CACHE=false），跳过预热")
        return
    start_cache_warm_up()


async def scheduled_refresh_cache() -> None:
    """定时任务入口：检查热门指令榜单与日期变化，按需在后台更新磁盘缓存。"""
    if not config.larkhelp_cache:
        return
    try:
        await refresh_cache(force=False)
    except Exception:
        logger.opt(exception=True).warning("LarkHelp 帮助面板热门榜单定时刷新失败")


if config.larkhelp_cache_refresh_interval > 0:
    scheduler.scheduled_job(
        "interval",
        seconds=config.larkhelp_cache_refresh_interval,
        id="larkhelp_refresh_panel_cache",
        coalesce=True,
        max_instances=1,
    )(scheduled_refresh_cache)
