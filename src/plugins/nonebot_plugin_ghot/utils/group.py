from sqlalchemy import select

from nonebot_plugin_bots.models import GroupBind
from nonebot_plugin_orm import async_scoped_session

QQ_GROUP_PREFIX = "qq_"


def _strip_qq_prefix(group_id: str) -> str | None:
    """去掉 QQ 群键的平台前缀；不是 QQ 群键时返回 None。"""
    if not group_id.startswith(QQ_GROUP_PREFIX):
        return None
    return group_id[len(QQ_GROUP_PREFIX) :]


def _build_bind_keys(bind: GroupBind, group_id: str) -> list[str]:
    """按「群号在前、openid 在后」的顺序拼出同一物理群的全部群键。"""
    keys: list[str] = []
    if bind.group_qq_number:
        keys.append(f"{QQ_GROUP_PREFIX}{bind.group_qq_number}")
    if bind.group_openid:
        keys.append(f"{QQ_GROUP_PREFIX}{bind.group_openid}")
    if group_id not in keys:
        keys.append(group_id)
    return keys


async def _find_bind(session: async_scoped_session, group_key: str) -> GroupBind | None:
    """按群号或 group_openid 查询群绑定记录。"""
    if group_key.isdigit():
        return await session.scalar(select(GroupBind).where(GroupBind.group_qq_number == group_key))
    return await session.scalar(select(GroupBind).where(GroupBind.group_openid == group_key))


async def resolve_group_keys(session: async_scoped_session, group_id: str) -> list[str]:
    """返回同一物理群在消息表中的全部群键，归一化后的主键在最前。

    QQ 官方机器人的群消息以 `qq_<group_openid>` 记录，OneBot 以 `qq_<群号>` 记录，
    两者通过 `nonebot_plugin_bots` 的 `GroupBind` 绑定。这里把它们视作同一个群，
    避免同一物理群被拆成两份热度、并在群热度排名里占据两个位次。
    未绑定（或非 QQ）的群只返回自身。
    """
    raw_group_id = _strip_qq_prefix(group_id)
    if raw_group_id is None:
        return [group_id]
    bind = await _find_bind(session, raw_group_id)
    if bind is None:
        return [group_id]
    return _build_bind_keys(bind, group_id)


async def get_group_key_aliases(session: async_scoped_session) -> dict[str, str]:
    """返回 `qq_<group_openid>` -> `qq_<群号>` 的映射，用于合并统计口径。"""
    binds = (await session.scalars(select(GroupBind))).all()
    aliases: dict[str, str] = {}
    for bind in binds:
        if bind.group_qq_number and bind.group_openid:
            aliases[f"{QQ_GROUP_PREFIX}{bind.group_openid}"] = f"{QQ_GROUP_PREFIX}{bind.group_qq_number}"
    return aliases


def normalize_group_key(group_id: str, aliases: dict[str, str]) -> str:
    """把群键折叠到统一的统计键。"""
    return aliases.get(group_id, group_id)
