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

import re

from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.log import logger
from nonebot.message import event_preprocessor
from nonebot_plugin_alconna import Alconna, Args, Arparma, Subcommand, on_alconna
from nonebot_plugin_larkhelp.__main__ import get_help_list
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.subaccount import get_main_account
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import CommandAlias

lang = LangHelper()

driver = get_driver()

# 指令前缀（如 "/"），按长度降序排列，优先匹配更长的前缀
_COMMAND_STARTS: tuple[str, ...] = tuple(sorted(driver.config.command_start, key=len, reverse=True))

# 别名指令自身名称，预处理器需跳过，避免递归改写
ALIAS_COMMAND = "alias"

# 变量命名规则：字母或下划线开头，仅包含字母、数字、下划线
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 内存缓存：所有已注册的别名（跨用户），避免每条消息都查询数据库
_alias_names: set[str] = set()


@driver.on_startup
async def _load_alias_names() -> None:
    """启动时加载全部别名到内存缓存"""
    global _alias_names
    async with get_session() as session:
        result = await session.execute(select(CommandAlias.alias))
        _alias_names = set(result.scalars().all())
    logger.info(f"[CommandAlias] 已加载 {len(_alias_names)} 个指令别名")


@event_preprocessor
async def apply_command_alias(event: Event) -> None:
    """将消息中用户自定义的指令别名改写为原指令名

    仅处理以指令前缀开头、且首词命中用户别名的消息：
    读取并覆写消息中的第一个文本消息段，使其能被 Alconna 正常匹配。
    """
    try:
        if event.get_type() != "message":
            return
    except NotImplementedError:
        return
    try:
        user_id = await get_main_account(event.get_user_id())
    except (ValueError, NotImplementedError):
        return
    try:
        message = event.get_message()
    except (NotImplementedError, ValueError):
        return
    if not message:
        return
    # 找到第一个文本消息段
    text_segment = next((segment for segment in message if segment.type == "text"), None)
    if text_segment is None:
        return
    text = str(text_segment.data.get("text", ""))
    if not text:
        return
    for prefix in _COMMAND_STARTS:
        if not text.startswith(prefix):
            continue
        rest = text[len(prefix) :]
        word = rest.split(maxsplit=1)[0] if rest else ""
        if not word or word == ALIAS_COMMAND or word not in _alias_names:
            return
        # 命中候选别名，查库确认该用户确实拥有此别名
        async with get_session() as session:
            row = await session.get(CommandAlias, {"user_id": user_id, "alias": word})
        if row is None:
            return
        # 覆写第一个文本段：将别名替换为原指令
        text_segment.data["text"] = f"{prefix}{row.command}{rest[len(word) :]}"
        logger.debug(f"[CommandAlias] {user_id}: {prefix}{word} -> {prefix}{row.command}")
        return


# ============================================================
# /alias 指令
# ============================================================

alias_cmd = on_alconna(
    Alconna(
        "alias",
        Subcommand("rm", Args["alias", str]),
        Subcommand("list"),
        Args["command?", str]["alias_name?", str],
    ),
    use_cmd_start=True,
    priority=5,
)


@alias_cmd.assign("rm")
async def remove_alias(alias: str, user_id: str = get_user_id()) -> None:
    """删除指定别名"""
    async with get_session() as session:
        row = await session.get(CommandAlias, {"user_id": user_id, "alias": alias})
        if row is None:
            await lang.finish("alias.removed_not_found", user_id, alias=alias)
        await session.delete(row)
        await session.commit()
    _alias_names.discard(alias)
    await lang.finish("alias.removed", user_id, alias=alias)


@alias_cmd.assign("list")
async def list_aliases(user_id: str = get_user_id()) -> None:
    """列出当前用户的全部别名"""
    async with get_session() as session:
        rows = (await session.scalars(select(CommandAlias).where(CommandAlias.user_id == user_id))).all()
    if not rows:
        await lang.finish("alias.list_empty", user_id)
    title = await lang.text("alias.list_title", user_id, count=len(rows))
    items = [await lang.text("alias.list_item", user_id, alias=row.alias, command=row.command) for row in rows]
    await alias_cmd.finish("\n".join([title, *items]))


@alias_cmd.assign("$main")
async def create_alias(result: Arparma, user_id: str = get_user_id()) -> None:
    """创建指令别名"""
    command = result.query("command")
    alias_name = result.query("alias_name")
    if not command or not alias_name:
        await lang.finish("alias.usage", user_id)

    # 1. 原指令必须是 help/man 中登记的指令
    available_commands = get_help_list()
    if command not in available_commands:
        await lang.finish("alias.command_not_found", user_id, command=command)

    # 2. 别名需遵循变量命名规则
    if not _VARIABLE_NAME_RE.fullmatch(alias_name):
        await lang.finish("alias.invalid_name", user_id, alias=alias_name)

    # 3. 别名不能与原指令相同
    if alias_name == command:
        await lang.finish("alias.same_as_command", user_id, command=command)

    # 4. 别名不能与已有指令名重复
    if alias_name in available_commands:
        await lang.finish("alias.name_conflict_command", user_id, alias=alias_name)

    # 5. 同一用户不能重复使用同一别名
    async with get_session() as session:
        row = await session.get(CommandAlias, {"user_id": user_id, "alias": alias_name})
        if row is not None:
            await lang.finish("alias.name_conflict_alias", user_id, alias=alias_name, command=row.command)
        session.add(CommandAlias(user_id=user_id, alias=alias_name, command=command))
        await session.commit()
    _alias_names.add(alias_name)
    await lang.finish("alias.created", user_id, alias=alias_name, command=command)
