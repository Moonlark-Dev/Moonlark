"""``/lastseen`` 在 QQ 官方适配器下的目标用户解析回归测试。

QQ 官方适配器的 ``At`` 目标是适配器原生 openid（群聊是 member_openid），而
``LastSeenRecord`` 以主账号 ID（``get_main_account()`` 映射后的 QQ 号）为键存储
（写入走 ``get_user_id()``，已经是主账号）。此前命令直接拿 ``At.target`` 查询：

- 已映射为 QQ 号的用户会被查到映射前遗留的 openid 旧记录，表现为「记录值不更新」；
- 新用户则直接查不到记录。

修复后查询前先把原生 ID 解析成主账号，昵称仍按原生 ID 取（平台接口只认 openid）。
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

MAIN_ACCOUNT = "1747433912"
OPENID = "2FB3AC4036B00194FB277954260A2860"


@pytest.fixture
def last_seen() -> ModuleType:
    from nonebot_plugin_last_seen import __main__ as module

    return module


def _patch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    mapped_id: "str | Callable[[str], str]",
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    fake_lang = MagicMock()
    fake_lang.text = AsyncMock(return_value="text")
    fake_lang.finish = AsyncMock()
    monkeypatch.setattr(module, "lang", fake_lang)

    nickname = AsyncMock(return_value="nick")
    monkeypatch.setattr(module, "get_nickname", nickname)

    info = AsyncMock(return_value={"location": "loc", "time_diff": "diff", "time_point": "time"})
    monkeypatch.setattr(module, "get_last_seen_info", info)

    resolve: Callable[[str], str] = mapped_id if callable(mapped_id) else (lambda _user_id: mapped_id)
    main_account = AsyncMock(side_effect=resolve)
    monkeypatch.setattr(module, "get_main_account", main_account)
    return nickname, info, main_account


async def _run(module: ModuleType, match: Any) -> None:
    await module.handle_lastseen(
        MagicMock(),
        MagicMock(),
        match,
        sender_id=MAIN_ACCOUNT,
        is_private=False,
        group_id="qq_GROUP_OPENID",
    )


@pytest.mark.asyncio
async def test_at_target_is_resolved_to_main_account(last_seen: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """At 的 openid 先映射成主账号再查记录；昵称仍用原生 openid 取"""
    from nonebot_plugin_alconna import At, Match

    nickname, info, main_account = _patch_dependencies(monkeypatch, last_seen, MAIN_ACCOUNT)

    await _run(last_seen, Match(At("user", OPENID), True))

    main_account.assert_awaited_once_with(OPENID)
    assert nickname.await_args.args[0] == OPENID
    # 全局与本群两条记录都必须用主账号查询
    assert [call.args[1] for call in info.await_args_list] == [MAIN_ACCOUNT, MAIN_ACCOUNT]


@pytest.mark.asyncio
async def test_string_target_is_resolved_to_main_account(
    last_seen: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直接输入的用户 ID（如 QQ 号）同样走一次映射，未映射时原样返回"""
    from nonebot_plugin_alconna import Match

    nickname, info, main_account = _patch_dependencies(monkeypatch, last_seen, MAIN_ACCOUNT)

    await _run(last_seen, Match("10001", True))

    main_account.assert_awaited_once_with("10001")
    assert nickname.await_args.args[0] == "10001"
    assert [call.args[1] for call in info.await_args_list] == [MAIN_ACCOUNT, MAIN_ACCOUNT]


@pytest.mark.asyncio
async def test_unmapped_user_keeps_native_id(last_seen: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有主账号映射的纯 QQ 官方用户：查询仍用原生 openid"""
    from nonebot_plugin_alconna import At, Match

    nickname, info, main_account = _patch_dependencies(monkeypatch, last_seen, lambda user_id: user_id)

    await _run(last_seen, Match(At("user", OPENID), True))

    main_account.assert_awaited_once_with(OPENID)
    assert nickname.await_args.args[0] == OPENID
    assert [call.args[1] for call in info.await_args_list] == [OPENID, OPENID]
