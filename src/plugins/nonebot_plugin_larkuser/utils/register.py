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

"""用户注册。

Moonlark 不再提供独立的 ``register`` 指令：任何需要注册的指令在被使用时都会
通过 :func:`ensure_registered` 自动完成注册，整个过程对用户完全静默。

昵称优先取平台展示名（:class:`nonebot_plugin_userinfo.UserInfo.user_name`），
拿不到时回退为 ``用户-{user_id}``；不再发送许可协议提示，也不再等待用户输入昵称。
"""

import json
from datetime import datetime
from typing import Optional

from nonebot.log import logger
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot_plugin_userinfo import UserInfo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import UserData
from ..user.utils import is_user_registered


def default_nickname(user_id: str) -> str:
    """返回用户没有可用昵称时使用的兜底昵称。

    ``UserData.nickname`` 是非空列，任何情况下都不能写入 ``NULL``，
    因此注册流程统一使用 ``用户-{user_id}`` 兜底，与
    :meth:`nonebot_plugin_larkuser.user.registered.MoonlarkRegisteredUser.setup_user`
    中的展示兜底保持一致。
    """
    return f"用户-{user_id}"


def resolve_nickname(user: Optional[UserInfo], user_id: str) -> str:
    """从平台用户信息中取昵称，取不到时回退为 :func:`default_nickname`。"""
    if user is not None and user.user_name and (nickname := user.user_name.strip()):
        return nickname
    return default_nickname(user_id)


async def register_user(
    session: AsyncSession | async_scoped_session,
    user_id: str,
    user: Optional[UserInfo] = None,
) -> str:
    """静默注册用户并返回其昵称。

    已注册的用户不会被覆盖：直接返回现有昵称，不修改注册时间与昵称。
    多个指令并发触发同一用户的注册时，写入失败的一方会收到 ``IntegrityError``，
    回滚后按「已注册」处理并复用已有数据。

    :param session: 数据库会话
    :param user_id: 用户 ID（主账号 ID）
    :param user: 平台用户信息，用于获取昵称；为空时使用兜底昵称
    :return: 写入（或已存在）的昵称
    """
    if (data := await session.get(UserData, user_id)) is not None:
        nickname = data.nickname or default_nickname(user_id)
        if data.register_time is None:
            # 兼容历史上已存在 UserData 行、但尚未完成注册的数据
            data.register_time = datetime.now()
            if not data.nickname:
                data.nickname = nickname = resolve_nickname(user, user_id)
            await session.commit()
        return nickname
    nickname = resolve_nickname(user, user_id)
    session.add(
        UserData(
            user_id=user_id,
            nickname=nickname,
            register_time=datetime.now(),
            config=json.dumps({"lock_nickname": False}),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        logger.debug(f"用户 {user_id} 已被并发注册，沿用已有数据")
        await session.rollback()
        data = await session.get(UserData, user_id)
        if data is None:
            raise
        return data.nickname or default_nickname(user_id)
    return nickname


async def ensure_registered(user_id: str, user: Optional[UserInfo] = None) -> bool:
    """确保用户已注册；未注册时静默注册。

    需要注册的指令与需要读取已注册用户列表的指令都通过本函数保证调用方已注册。

    :param user_id: 用户 ID（主账号 ID）
    :param user: 平台用户信息，用于获取昵称；为空时使用兜底昵称
    :return: 本次是否真的写入了注册数据
    """
    if await is_user_registered(user_id):
        return False
    async with get_session() as session:
        await register_user(session, user_id, user)
    return True
