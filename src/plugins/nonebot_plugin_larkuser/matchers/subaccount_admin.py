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

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot_plugin_larkutils import (
    get_user_id,
    is_user_superuser,
    set_main_account,
    get_main_account,
    get_sub_accounts,
    remove_main_account,
    remove_all_sub_accounts,
)
from nonebot_plugin_orm import get_session

from ..lang import lang
from ..models import UserData, GuestUser
from ..utils.waiter import prompt as get_confirmation

subaccount_admin = on_command(
    "subaccount",
    aliases={"子账号"},
    permission=None,
)


async def _get_user_nickname(user_id: str) -> str:
    """尝试获取用户昵称，用于展示"""
    async with get_session() as session:
        user_data = await session.get(UserData, {"user_id": user_id})
        if user_data is not None and user_data.nickname:
            return user_data.nickname
        guest_data = await session.get(GuestUser, {"user_id": user_id})
        if guest_data is not None and guest_data.nickname:
            return guest_data.nickname
    return f"用户-{user_id[-4:]}"


@subaccount_admin.handle()
async def _(
    args: Message = CommandArg(),
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
) -> None:
    if not is_superuser:
        await lang.finish("subaccount_admin.permission_denied", user_id)

    text = args.extract_plain_text().strip()
    if not text:
        await lang.finish("subaccount_admin.usage", user_id)

    parts = text.split()
    action = parts[0].lower()

    if action == "view" or action == "状态":
        if len(parts) < 2:
            await lang.finish("subaccount_admin.usage", user_id)
        target_id = parts[1]
        await _handle_view(target_id, user_id)

    elif action == "bind" or action == "绑定":
        if len(parts) < 3:
            await lang.finish("subaccount_admin.usage", user_id)
        sub_id = parts[1]
        main_id = parts[2]
        await _handle_bind(sub_id, main_id, user_id)

    elif action == "unbind" or action == "解绑":
        if len(parts) >= 3 and (parts[2] == "--all" or parts[2] == "全部"):
            await _handle_unbind_all(parts[1], user_id)
        elif len(parts) >= 2:
            await _handle_unbind(parts[1], user_id)
        else:
            await lang.finish("subaccount_admin.usage", user_id)

    else:
        await lang.finish("subaccount_admin.usage", user_id)


async def _handle_view(target_id: str, user_id: str) -> None:
    """查看指定 ID 的绑定情况"""
    main_account = await get_main_account(target_id)
    sub_accounts = await get_sub_accounts(target_id)
    nickname = await _get_user_nickname(target_id)

    if main_account != target_id:
        # 该账号是子账号
        main_nickname = await _get_user_nickname(main_account)
        await lang.finish(
            "subaccount_admin.view_is_sub",
            user_id,
            target_id,
            nickname,
            main_account,
            main_nickname,
        )
    elif sub_accounts:
        # 该账号是主账号且有子账号
        sub_info = []
        for sub_id in sub_accounts:
            sub_nick = await _get_user_nickname(sub_id)
            sub_info.append(f"{sub_id} ({sub_nick})")
        sub_list = "\n".join(f"  - {s}" for s in sub_info)
        await lang.finish(
            "subaccount_admin.view_has_subs",
            user_id,
            target_id,
            nickname,
            len(sub_accounts),
            sub_list,
        )
    else:
        # 既不是子账号也没有子账号
        await lang.finish(
            "subaccount_admin.view_none",
            user_id,
            target_id,
            nickname,
        )


async def _handle_bind(sub_id: str, main_id: str, user_id: str) -> None:
    """将 sub_id 绑定为 main_id 的子账号"""
    # 检查 sub_id 是否已经有主账号
    existing_main = await get_main_account(sub_id)
    if existing_main != sub_id:
        existing_main_nick = await _get_user_nickname(existing_main)
        sub_nick = await _get_user_nickname(sub_id)
        await lang.finish(
            "subaccount_admin.bind_already_bound",
            user_id,
            sub_id,
            sub_nick,
            existing_main,
            existing_main_nick,
        )

    # 检查 main_id 是否存在（通过能否查到 UserData 或 GuestUser 来判断）
    # 但也可以对任意 ID 进行绑定，不过为了合理，还是检查一下
    async with get_session() as session:
        main_data = await session.get(UserData, {"user_id": main_id})
        if main_data is None:
            guest_data = await session.get(GuestUser, {"user_id": main_id})
            if guest_data is None:
                await lang.finish(
                    "subaccount_admin.bind_target_not_found",
                    user_id,
                    main_id,
                )

    sub_nick = await _get_user_nickname(sub_id)
    main_nick = await _get_user_nickname(main_id)

    # 发送确认消息
    await lang.send(
        "subaccount_admin.bind_confirm",
        user_id,
        sub_id,
        sub_nick,
        main_id,
        main_nick,
    )
    await get_confirmation(
        await lang.text("subaccount_admin.confirm_prompt", user_id),
        user_id,
        checker=lambda msg: msg.strip().lower() in ("y", "yes", "是", "确认"),
        retry=2,
    )

    await set_main_account(sub_id, main_id)
    await lang.finish(
        "subaccount_admin.bind_success",
        user_id,
        sub_id,
        sub_nick,
        main_id,
        main_nick,
    )


async def _handle_unbind(sub_id: str, user_id: str) -> None:
    """解绑指定子账号的主账号"""
    existing_main = await get_main_account(sub_id)
    if existing_main == sub_id:
        sub_nick = await _get_user_nickname(sub_id)
        await lang.finish(
            "subaccount_admin.unbind_not_bound",
            user_id,
            sub_id,
            sub_nick,
        )

    sub_nick = await _get_user_nickname(sub_id)
    main_nick = await _get_user_nickname(existing_main)

    await lang.send(
        "subaccount_admin.unbind_confirm",
        user_id,
        sub_id,
        sub_nick,
        existing_main,
        main_nick,
    )
    await get_confirmation(
        await lang.text("subaccount_admin.confirm_prompt", user_id),
        user_id,
        checker=lambda msg: msg.strip().lower() in ("y", "yes", "是", "确认"),
        retry=2,
    )

    await remove_main_account(sub_id)
    await lang.finish(
        "subaccount_admin.unbind_success",
        user_id,
        sub_id,
        sub_nick,
        existing_main,
        main_nick,
    )


async def _handle_unbind_all(main_id: str, user_id: str) -> None:
    """解绑指定主账号的所有子账号"""
    sub_accounts = await get_sub_accounts(main_id)
    if not sub_accounts:
        main_nick = await _get_user_nickname(main_id)
        await lang.finish(
            "subaccount_admin.unbind_all_no_subs",
            user_id,
            main_id,
            main_nick,
        )

    main_nick = await _get_user_nickname(main_id)
    sub_info = []
    for sub_id in sub_accounts:
        sub_nick = await _get_user_nickname(sub_id)
        sub_info.append(f"  - {sub_id} ({sub_nick})")
    sub_list = "\n".join(sub_info)

    await lang.send(
        "subaccount_admin.unbind_all_confirm",
        user_id,
        main_id,
        main_nick,
        len(sub_accounts),
        sub_list,
    )
    await get_confirmation(
        await lang.text("subaccount_admin.confirm_prompt", user_id),
        user_id,
        checker=lambda msg: msg.strip().lower() in ("y", "yes", "是", "确认"),
        retry=2,
    )

    removed = await remove_all_sub_accounts(main_id)
    await lang.finish(
        "subaccount_admin.unbind_all_success",
        user_id,
        main_id,
        main_nick,
        len(removed),
    )
