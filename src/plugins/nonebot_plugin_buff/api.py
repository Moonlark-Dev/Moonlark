"""Buff 系统的读写接口。

对外提供附着一个 buff、查询、消耗次数、移除等操作，所有数据都存放在
`nonebot_plugin_buff_attachment` 表中。已过期（时间耗尽或次数耗尽）的附着
会在每次读写时被清理。

同时存在时间与次数两个维度时，任意一个耗尽都会让整个 buff 消失。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Union

from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import delete, select

from .models import BuffAttachment
from .registry import BuffDefinition, ensure_buff_definition, get_buff_definition

Duration = Union[timedelta, int, float, None]


@dataclass
class BuffInfo:
    """一次 buff 附着的快照（不持有 ORM 对象）"""

    buff_id: str
    layers: int
    expires_at: Optional[datetime]
    remaining_count: Optional[int]
    created_at: datetime
    updated_at: datetime

    @property
    def definition(self) -> Optional[BuffDefinition]:
        return get_buff_definition(self.buff_id)

    @property
    def is_expired(self) -> bool:
        return is_attachment_expired(self.expires_at, self.remaining_count)

    @property
    def remaining_seconds(self) -> Optional[float]:
        """剩余时间（秒）；没有时间维度时返回 None，已过期返回 0"""
        if self.expires_at is None:
            return None
        return max((self.expires_at - datetime.now()).total_seconds(), 0.0)

    @classmethod
    def from_model(cls, row: BuffAttachment) -> "BuffInfo":
        return cls(
            buff_id=row.buff_id,
            layers=row.layers,
            expires_at=row.expires_at,
            remaining_count=row.remaining_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def is_attachment_expired(
    expires_at: Optional[datetime], remaining_count: Optional[int], now: Optional[datetime] = None
) -> bool:
    """判断一次附着是否已经耗尽（时间或次数任意一个用尽）"""
    now = now or datetime.now()
    if expires_at is not None and expires_at <= now:
        return True
    if remaining_count is not None and remaining_count <= 0:
        return True
    return False


def _to_timedelta(duration: Duration) -> Optional[timedelta]:
    if duration is None:
        return None
    if isinstance(duration, timedelta):
        return duration
    return timedelta(seconds=float(duration))


async def _get_row(session: AsyncSession, user_id: str, buff_id: str) -> Optional[BuffAttachment]:
    return await session.scalar(
        select(BuffAttachment).where(BuffAttachment.user_id == user_id, BuffAttachment.buff_id == buff_id)
    )


async def purge_expired(session: AsyncSession, user_id: Optional[str] = None) -> int:
    """清理已过期的附着，返回清理数量"""
    now = datetime.now()
    stmt = select(BuffAttachment)
    if user_id is not None:
        stmt = stmt.where(BuffAttachment.user_id == user_id)
    count = 0
    for row in (await session.scalars(stmt)).all():
        if is_attachment_expired(row.expires_at, row.remaining_count, now):
            await session.delete(row)
            count += 1
    return count


async def attach_buff(
    user_id: str,
    buff_id: str,
    duration: Duration = None,
    count: Optional[int] = None,
    layers: int = 1,
) -> BuffInfo:
    """给用户附着一个 buff

    - 不支持叠加（`max_layers == 1`）时，重复附着会刷新时长与次数；
    - 支持叠加时，重复附着会累加层数（不超过 `max_layers`），
      时间维度在剩余时间的基础上累加，次数维度直接累加；
    - `duration` / `count` 为 None 时使用定义中的默认值；两者都没有表示
      该附着既不会超时也不会耗尽次数。

    Args:
        user_id: 用户 ID
        buff_id: buff 标识
        duration: 时间维度，支持 `timedelta` 或秒数
        count: 次数维度
        layers: 本次附着的层数，至少为 1
    """
    definition = ensure_buff_definition(buff_id)
    max_layers = max(definition.max_layers, 1)
    delta = _to_timedelta(duration) if duration is not None else definition.default_duration
    total_count = count if count is not None else definition.default_count
    if total_count is not None:
        total_count = max(int(total_count), 1)
    add_layers = max(int(layers), 1)
    now = datetime.now()

    async with get_session() as session:
        await purge_expired(session, user_id)
        row = await _get_row(session, user_id, buff_id)
        if row is None:
            row = BuffAttachment(
                user_id=user_id,
                buff_id=buff_id,
                layers=min(add_layers, max_layers),
                expires_at=now + delta if delta is not None else None,
                remaining_count=total_count,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        elif max_layers <= 1:
            row.layers = 1
            row.expires_at = now + delta if delta is not None else None
            row.remaining_count = total_count
            row.updated_at = now
        else:
            row.layers = min(row.layers + add_layers, max_layers)
            if delta is not None:
                base = row.expires_at if row.expires_at and row.expires_at > now else now
                row.expires_at = base + delta
            if total_count is not None:
                row.remaining_count = (row.remaining_count or 0) + total_count
            row.updated_at = now
        # 必须在 commit 之前取出快照：commit 会使 ORM 实例过期，
        # 之后再读取属性会触发同步 IO 并抛出 MissingGreenlet
        info = BuffInfo.from_model(row)
        await session.commit()
        return info


async def get_buff_attachment(user_id: str, buff_id: str) -> Optional[BuffInfo]:
    """获取用户某个 buff 的当前附着；不存在或已过期返回 None"""
    async with get_session() as session:
        await purge_expired(session, user_id)
        await session.commit()
        row = await _get_row(session, user_id, buff_id)
        return BuffInfo.from_model(row) if row is not None else None


async def get_buff_attachments(user_id: str) -> list[BuffInfo]:
    """获取用户当前所有生效中的附着"""
    async with get_session() as session:
        await purge_expired(session, user_id)
        await session.commit()
        rows = (
            await session.scalars(
                select(BuffAttachment).where(BuffAttachment.user_id == user_id).order_by(BuffAttachment.created_at)
            )
        ).all()
        return [BuffInfo.from_model(row) for row in rows]


async def has_buff(user_id: str, buff_id: str) -> bool:
    """判断用户是否正受到某个 buff 影响"""
    return await get_buff_attachment(user_id, buff_id) is not None


async def get_buff_layers(user_id: str, buff_id: str) -> int:
    """获取用户某个 buff 的层数；未附着返回 0"""
    attachment = await get_buff_attachment(user_id, buff_id)
    return attachment.layers if attachment is not None else 0


async def consume_buff(user_id: str, buff_id: str, amount: int = 1) -> bool:
    """消耗 buff 的可触发次数

    未附着或已过期返回 False。没有次数维度的 buff 视为一直生效，直接返回
    True 且不减少任何计数。

    Args:
        user_id: 用户 ID
        buff_id: buff 标识
        amount: 本次消耗的次数
    """
    amount = max(int(amount), 1)
    async with get_session() as session:
        await purge_expired(session, user_id)
        row = await _get_row(session, user_id, buff_id)
        if row is None or is_attachment_expired(row.expires_at, row.remaining_count):
            await session.commit()
            return False
        if row.remaining_count is not None:
            row.remaining_count -= amount
            row.updated_at = datetime.now()
            if row.remaining_count <= 0:
                await session.delete(row)
        await session.commit()
        return True


async def detach_buff(user_id: str, buff_id: str, layers: Optional[int] = None) -> bool:
    """移除 buff；`layers` 为 None 时整层移除，否则只减少指定层数

    返回是否真的移除了内容。
    """
    async with get_session() as session:
        await purge_expired(session, user_id)
        row = await _get_row(session, user_id, buff_id)
        if row is None:
            await session.commit()
            return False
        if layers is None or layers >= row.layers:
            await session.delete(row)
        else:
            row.layers -= max(int(layers), 1)
            row.updated_at = datetime.now()
        await session.commit()
        return True


async def clear_buffs(user_id: str) -> int:
    """清空用户所有 buff，返回清理数量"""
    async with get_session() as session:
        result = await session.execute(delete(BuffAttachment).where(BuffAttachment.user_id == user_id))
        await session.commit()
        return int(result.rowcount or 0)
