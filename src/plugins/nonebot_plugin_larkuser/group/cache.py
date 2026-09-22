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

"""QQ 官方 Bot 群聊缓存。

群成员列表接口存在分页与频率限制（60 QPM，每页最多 30 条），因此这里把接口
结果落到数据库里做缓存，由 :mod:`nonebot_plugin_larkuser.group.sync` 周期性刷新，
群聊相关功能只读缓存，避免每次都直接打接口。

缓存同时承担两个额外职责：

- 用群成员列表里的昵称补全没有昵称的用户（注册用户昵称为空时填入，
  未注册用户写入 :class:`~nonebot_plugin_larkuser.models.GuestUser`）；
- 提供「昵称 → 成员 openid」映射，供 Chat 会话解析 @ 使用。
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

from nonebot import get_bots, logger
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..config import config
from ..models import GuestUser, QQGroupInfo, QQGroupMember, UserData
from .client import QQGroupAPIError, fetch_all_group_members, fetch_group_info
from .types import QQGroupInfo as QQGroupInfoData
from .types import QQGroupMemberInfo

# 自动补全的昵称来源标记，写入 UserData.config[NICK_SOURCE_KEY]
NICK_SOURCE_KEY = "nick_source"
NICK_SOURCE_GROUP_MEMBER = "group_member"

# 单次 SQL IN 查询的元素上限（兼容 SQLite 的变量数限制）
_SQL_CHUNK_SIZE = 200

# 每个群同一时间只允许一次同步
_sync_locks: dict[str, asyncio.Lock] = {}
# 本进程内已经触发过同步的群，避免每条消息都去查库/打接口
_triggered_groups: set[str] = set()
_background_tasks: set[asyncio.Task] = set()


def _now() -> datetime:
    return datetime.now()


def _is_expired(timestamp: Optional[datetime], ttl_seconds: int) -> bool:
    if timestamp is None:
        return True
    return _now() - timestamp > timedelta(seconds=ttl_seconds)


def _get_sync_lock(group_openid: str) -> asyncio.Lock:
    lock = _sync_locks.get(group_openid)
    if lock is None:
        lock = _sync_locks[group_openid] = asyncio.Lock()
    return lock


def get_qq_bot(bot_id: str = "") -> Optional[QQBot]:
    """获取一个可用的 QQ 官方 Bot 实例。

    指定 ``bot_id`` 时只返回该 Bot：group_openid 由平台按应用分配，换一个 Bot
    查询同一个群必然取不到数据；不指定时返回任意一个在线的 QQ 官方 Bot。
    """
    bots = get_bots()
    if bot_id:
        bot = bots.get(bot_id)
        return bot if isinstance(bot, QQBot) else None
    for bot in bots.values():
        if isinstance(bot, QQBot):
            return bot
    return None


def _chunks(items: Sequence[str], size: int = _SQL_CHUNK_SIZE) -> list[Sequence[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def remember_group(group_openid: str, bot_id: str = "") -> None:
    """登记一个 QQ 群（不调用接口），已存在时只补全 bot_id。"""
    async with get_session() as session:
        record = await session.get(QQGroupInfo, {"group_openid": group_openid})
        if record is None:
            session.add(QQGroupInfo(group_openid=group_openid, bot_id=bot_id))
            await session.commit()
            logger.info(f"[larkuser] 登记 QQ 群 {group_openid}（bot={bot_id or '未知'}）")
            return
        if bot_id and record.bot_id != bot_id:
            record.bot_id = bot_id
            await session.commit()


async def get_group_record(group_openid: str) -> Optional[QQGroupInfoData]:
    """读取群的缓存信息（不调用接口），群未被登记时返回 ``None``。"""
    async with get_session() as session:
        record = await session.get(QQGroupInfo, {"group_openid": group_openid})
        if record is None:
            return None
        return QQGroupInfoData(
            group_openid=record.group_openid,
            group_name=record.group_name,
            description=record.description,
            member_count=record.member_count,
            info_updated_at=record.info_updated_at,
            members_synced_at=record.members_synced_at,
        )


async def get_cached_group_members(group_openid: str) -> list[QQGroupMemberInfo]:
    """读取缓存的群成员列表（不调用接口）。"""
    async with get_session() as session:
        rows = await session.scalars(
            select(QQGroupMember)
            .where(QQGroupMember.group_openid == group_openid)
            .order_by(QQGroupMember.member_openid),
        )
        return [
            QQGroupMemberInfo(
                member_openid=row.member_openid,
                nickname=row.nickname,
                role=row.role,
                is_bot=row.is_bot,
                joined_at=row.joined_at,
                union_openid=row.union_openid,
            )
            for row in rows
        ]


async def get_group_member(group_openid: str, member_openid: str) -> Optional[QQGroupMemberInfo]:
    """按成员 openid 读取缓存的群成员信息，未缓存时返回 ``None``。"""
    async with get_session() as session:
        row = await session.get(QQGroupMember, {"group_openid": group_openid, "member_openid": member_openid})
        if row is None:
            return None
        return QQGroupMemberInfo(
            member_openid=row.member_openid,
            nickname=row.nickname,
            role=row.role,
            is_bot=row.is_bot,
            joined_at=row.joined_at,
            union_openid=row.union_openid,
        )


async def get_group_name(bot: QQBot, group_openid: str) -> Optional[str]:
    """获取群名称：优先使用缓存，缓存缺失或过期时调用接口刷新。"""
    record = await get_group_record(group_openid)
    if (
        record is not None
        and record.group_name
        and not _is_expired(record.info_updated_at, config.qq_group_info_cache_ttl)
    ):
        return record.group_name
    info = await refresh_group_info(bot, group_openid)
    if info is not None and info.group_name:
        return info.group_name
    return record.group_name if record is not None and record.group_name else None


async def refresh_group_info(bot: QQBot, group_openid: str) -> Optional[QQGroupInfoData]:
    """调用接口刷新群基本信息，失败时返回 ``None``（错误信息记录到缓存表中）。"""
    try:
        info = await fetch_group_info(bot, group_openid)
    except QQGroupAPIError as e:
        await _mark_sync_failed(group_openid, "群信息", str(e))
        return None
    async with get_session() as session:
        record = await session.get(QQGroupInfo, {"group_openid": group_openid})
        if record is None:
            record = QQGroupInfo(group_openid=group_openid, bot_id=bot.self_id)
            session.add(record)
        record.bot_id = bot.self_id
        record.group_name = info.group_name
        record.description = info.description
        if info.member_count:
            record.member_count = info.member_count
        record.info_updated_at = _now()
        record.last_error = ""
        await session.commit()
    return info


async def _mark_sync_failed(group_openid: str, subject: str, error: str) -> None:
    """记录一次同步失败，同时刷新对应时间戳以限制重试频率。"""
    logger.warning(f"[larkuser] 同步 QQ 群 {group_openid} 的{subject}失败: {error}")
    now = _now()
    async with get_session() as session:
        record = await session.get(QQGroupInfo, {"group_openid": group_openid})
        if record is None:
            record = QQGroupInfo(group_openid=group_openid)
            session.add(record)
        record.last_error = error[:512]
        if subject == "群信息":
            record.info_updated_at = now
        else:
            record.members_synced_at = now
        await session.commit()


async def _store_members(
    group_openid: str,
    members: list[QQGroupMemberInfo],
    synced_at: datetime,
) -> None:
    """把全量成员列表写入缓存，并删除已经退群的成员。"""
    async with get_session() as session:
        record = await session.get(QQGroupInfo, {"group_openid": group_openid})
        if record is None:
            record = QQGroupInfo(group_openid=group_openid)
            session.add(record)
        rows = await session.scalars(select(QQGroupMember).where(QQGroupMember.group_openid == group_openid))
        existing = {row.member_openid: row for row in rows}
        seen: set[str] = set()
        for member in members:
            seen.add(member.member_openid)
            row = existing.get(member.member_openid)
            if row is None:
                session.add(
                    QQGroupMember(
                        group_openid=group_openid,
                        member_openid=member.member_openid,
                        nickname=member.nickname,
                        role=member.role,
                        is_bot=member.is_bot,
                        joined_at=member.joined_at,
                        union_openid=member.union_openid,
                        updated_at=synced_at,
                    ),
                )
                continue
            row.nickname = member.nickname
            row.role = member.role
            row.is_bot = member.is_bot
            row.joined_at = member.joined_at
            row.union_openid = member.union_openid
            row.updated_at = synced_at
        for member_openid, row in existing.items():
            if member_openid not in seen:
                await session.delete(row)
        record.member_count = len(members)
        record.members_synced_at = synced_at
        record.last_error = ""
        await session.commit()


async def fill_user_nicknames(members: list[QQGroupMemberInfo]) -> int:
    """用群成员列表里的昵称补全没有昵称的用户，返回被更新的用户数。

    - 已经存在于 ``UserData``（已注册用户）但昵称为空时填入，并标记来源为
      ``group_member``，不会覆盖用户自己设置的昵称；
    - 未注册用户写入 ``GuestUser``，已存在时按最新昵称更新。
    """
    candidates = [member for member in members if member.nickname and not member.is_bot]
    if not candidates:
        return 0
    by_openid = {member.member_openid: member for member in candidates}
    updated = 0
    async with get_session() as session:
        for chunk in _chunks(list(by_openid)):
            user_rows = {
                row.user_id: row for row in await session.scalars(select(UserData).where(UserData.user_id.in_(chunk)))
            }
            guest_rows = {
                row.user_id: row for row in await session.scalars(select(GuestUser).where(GuestUser.user_id.in_(chunk)))
            }
            for member_openid in chunk:
                nickname = by_openid[member_openid].nickname
                if (user := user_rows.get(member_openid)) is not None:
                    if user.nickname:
                        continue
                    user.nickname = nickname
                    user.config = _with_nick_source(user.config)
                    updated += 1
                    continue
                if (guest := guest_rows.get(member_openid)) is None:
                    session.add(GuestUser(user_id=member_openid, nickname=nickname))
                    updated += 1
                elif guest.nickname != nickname:
                    guest.nickname = nickname
                    updated += 1
        await session.commit()
    return updated


def _with_nick_source(raw_config: Optional[str]) -> str:
    """在用户配置里写入自动补全来源标记。"""
    try:
        user_config: dict[str, Any] = json.loads(raw_config or "{}")
    except json.JSONDecodeError:
        user_config = {}
    user_config[NICK_SOURCE_KEY] = NICK_SOURCE_GROUP_MEMBER
    return json.dumps(user_config)


async def _resolve_user_nicknames(member_openids: list[str]) -> dict[str, str]:
    """批量查询成员在 Moonlark 中的昵称（已注册用户优先）。"""
    resolved: dict[str, str] = {}
    if not member_openids:
        return resolved
    async with get_session() as session:
        for chunk in _chunks(member_openids):
            guest_rows = await session.execute(
                select(GuestUser.user_id, GuestUser.nickname).where(GuestUser.user_id.in_(chunk)),
            )
            resolved.update({user_id: nickname for user_id, nickname in guest_rows if nickname})
            user_rows = await session.execute(
                select(UserData.user_id, UserData.nickname).where(UserData.user_id.in_(chunk)),
            )
            resolved.update({user_id: nickname for user_id, nickname in user_rows if nickname})
    return resolved


async def get_group_member_nickname_map(group_openid: str) -> dict[str, str]:
    """构造「昵称 → 成员 openid」映射，用于解析会话里出现的 @昵称。

    昵称优先取 Moonlark 中的昵称，没有时退回到群成员列表中的 QQ 昵称。
    """
    members = await get_cached_group_members(group_openid)
    if not members:
        return {}
    nicknames = await _resolve_user_nicknames([member.member_openid for member in members])
    result: dict[str, str] = {}
    for member in members:
        nickname = nicknames.get(member.member_openid) or member.nickname
        if nickname:
            result[nickname] = member.member_openid
    return result


async def refresh_group_members(bot: QQBot, group_openid: str) -> list[QQGroupMemberInfo]:
    """全量刷新群成员缓存（含分页、频率限制与昵称补全），返回最新成员列表。"""
    async with _get_sync_lock(group_openid):
        synced_at = _now()
        try:
            members = await fetch_all_group_members(
                bot,
                group_openid,
                max_members=config.qq_group_member_max_count,
            )
        except QQGroupAPIError as e:
            await _mark_sync_failed(group_openid, "群成员列表", str(e))
            return await get_cached_group_members(group_openid)
        await _store_members(group_openid, members, synced_at)
        updated = await fill_user_nicknames(members)
        logger.info(f"[larkuser] 已同步 QQ 群 {group_openid} 的 {len(members)} 名成员（补全 {updated} 个昵称）")
        return members


async def ensure_group_members(bot: QQBot, group_openid: str) -> list[QQGroupMemberInfo]:
    """确保群成员缓存可用：从未同步过（或缓存为空）时同步一次。

    同步失败同样会刷新同步时间戳，因此不会在每次调用时反复打接口，
    真正的周期性重试由 :func:`sync_all_groups` 按缓存有效期负责。
    """
    record = await get_group_record(group_openid)
    if record is None or record.members_synced_at is None:
        return await refresh_group_members(bot, group_openid)
    members = await get_cached_group_members(group_openid)
    if not members:
        return await refresh_group_members(bot, group_openid)
    return members


async def get_group_member_ids(bot: QQBot, group_openid: str) -> list[str]:
    """获取群成员 openid 列表（供 waifu 等插件使用）。"""
    return [member.member_openid for member in await ensure_group_members(bot, group_openid)]


async def _sync_group(bot: QQBot, group_openid: str) -> None:
    try:
        await remember_group(group_openid, bot.self_id)
        await refresh_group_info(bot, group_openid)
        await refresh_group_members(bot, group_openid)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception(f"[larkuser] 同步 QQ 群 {group_openid} 失败: {e}")


def request_group_sync(bot: QQBot, group_openid: str) -> None:
    """在后台同步一次群信息与群成员列表，不阻塞调用方。

    同一个群在本进程内只会被触发一次，后续刷新由周期性任务负责。
    """
    if group_openid in _triggered_groups:
        return
    _triggered_groups.add(group_openid)
    task = asyncio.ensure_future(_sync_group(bot, group_openid))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def ensure_group_known(bot: QQBot, group_openid: str) -> None:
    """登记群并触发一次后台同步（供收到群消息时调用）。"""
    if not group_openid:
        return
    if group_openid not in _triggered_groups:
        await remember_group(group_openid, bot.self_id)
    request_group_sync(bot, group_openid)


async def sync_all_groups() -> None:
    """周期任务：刷新所有已知群的群信息与群成员缓存。"""
    if not config.qq_group_sync_enabled:
        return
    async with get_session() as session:
        rows = await session.execute(
            select(QQGroupInfo.group_openid, QQGroupInfo.bot_id, QQGroupInfo.members_synced_at),
        )
        groups = list(rows)
    if not groups:
        return
    logger.debug(f"[larkuser] 开始同步 {len(groups)} 个 QQ 群的成员缓存")
    for group_openid, bot_id, members_synced_at in groups:
        if not _is_expired(members_synced_at, config.qq_group_member_cache_ttl):
            continue
        bot = get_qq_bot(bot_id)
        if bot is None:
            logger.debug(f"[larkuser] Bot {bot_id or '未记录'} 未连接，跳过群 {group_openid}")
            continue
        await _sync_group(bot, group_openid)
