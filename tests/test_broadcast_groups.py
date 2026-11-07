"""bc 自己维护的群列表测试

覆盖：
1. 收到群消息时写入/更新群列表与最后收消息时间；
2. bot_state 接口是白名单接口，调用失败时字段保持 nullable；
3. bot_state 调用成功时写入完整字段；
4. 广播群列表以这张表为准（不依赖 GroupBind）。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


async def _record(openid: str, qq: str | None = None) -> str:
    from nonebot_plugin_broadcast.groups import record_group_message

    return await record_group_message(qq, openid, datetime.now())


@pytest.mark.asyncio
async def test_record_group_message_tracks_last_message_time() -> None:
    from nonebot_plugin_broadcast.groups import get_group_snapshot, record_group_message

    seen_at = datetime(2026, 11, 7, 12, 0, 0)
    key = await record_group_message(None, "openid-tracked", seen_at)
    snapshot = await get_group_snapshot(key)

    assert key == "openid-tracked"
    assert snapshot is not None
    assert snapshot.group_openid == "openid-tracked"
    assert snapshot.last_message_at == seen_at


@pytest.mark.asyncio
async def test_record_group_message_prefers_qq_number_key() -> None:
    from nonebot_plugin_broadcast.groups import get_group_snapshot, record_group_message

    key = await record_group_message("70001", "openid-with-qq", datetime.now())
    snapshot = await get_group_snapshot("70001")

    assert key == "70001"
    assert snapshot is not None
    assert snapshot.group_qq_number == "70001"
    assert snapshot.group_openid == "openid-with-qq"


@pytest.mark.asyncio
async def test_bot_state_permission_error_keeps_fields_nullable(monkeypatch: pytest.MonkeyPatch) -> None:
    """白名单接口报 11253 时不能让群列表写入失败，字段保持 None"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_broadcast import groups

    await _record("openid-no-permission")
    qq_bot = MagicMock(spec=QQBot)
    qq_bot.self_id = "102"
    qq_bot.get_group_bot_state = AsyncMock(side_effect=RuntimeError("11253 应用无接口访问权限"))
    monkeypatch.setattr(groups, "_pick_qq_bot", lambda bot=None: qq_bot)

    allow = await groups.refresh_group_bot_state("openid-no-permission", force=True)
    snapshot = await groups.get_group_snapshot("openid-no-permission")

    assert allow is None
    assert snapshot is not None
    assert snapshot.allow_proactive_msg is None
    assert snapshot.recv_msg_setting is None
    assert snapshot.member_role is None
    assert snapshot.bot_state_checked_at is not None


@pytest.mark.asyncio
async def test_bot_state_success_stores_api_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_broadcast import groups

    await _record("openid-state")
    joined_at = datetime(2025, 6, 15, 14, 30, 0)
    state = SimpleNamespace(
        allow_proactive_msg=True,
        recv_msg_setting="all",
        member_role="admin",
        member_openid="bot-openid",
        joined_at=joined_at,
    )
    qq_bot = MagicMock(spec=QQBot)
    qq_bot.self_id = "102"
    qq_bot.get_group_bot_state = AsyncMock(return_value=state)
    monkeypatch.setattr(groups, "_pick_qq_bot", lambda bot=None: qq_bot)

    allow = await groups.refresh_group_bot_state("openid-state", force=True)
    snapshot = await groups.get_group_snapshot("openid-state")

    assert allow is True
    assert snapshot is not None
    assert snapshot.allow_proactive_msg is True
    assert snapshot.recv_msg_setting == "all"
    assert snapshot.member_role == "admin"
    assert snapshot.member_openid == "bot-openid"
    assert snapshot.joined_at == joined_at
    assert snapshot.bot_state_checked_at is not None


@pytest.mark.asyncio
async def test_available_groups_uses_learned_group_list(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """QQ 官方群没有群列表接口，收到过消息的群必须能通过那张表广播"""
    import nonebot_plugin_broadcast.__main__ as module
    import nonebot_plugin_broadcast.groups as groups
    from nonebot.adapters.qq import Bot as QQBot

    monkeypatch.setattr(module, "data_file", tmp_path / "data.json")
    await _record("openid-learned")

    qq_bot = MagicMock(spec=QQBot)
    qq_bot.self_id = "102"
    monkeypatch.setattr(module, "get_bots", lambda: {"102": qq_bot})
    monkeypatch.setattr(groups, "get_bots", lambda: {"102": qq_bot})

    available = await module.get_available_groups()
    assert available["openid-learned"] == [qq_bot]
