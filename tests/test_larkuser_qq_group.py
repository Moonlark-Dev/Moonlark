"""QQ 官方 Bot 群聊信息与群成员缓存（larkuser）的回归测试。

覆盖点：

- 群成员列表接口的解析、游标翻页与上限保护；
- 接口错误码（11253 无权限、429 频率限制）到异常类型的映射；
- 群成员缓存的写入 / 淘汰；
- 用群成员昵称补全 GuestUser（未注册用户）与昵称为空的已注册用户；
- 「昵称 -> 成员 openid」映射优先使用 Moonlark 昵称，供 Chat 解析 @ 使用；
- 群名称优先读取缓存，未过期时不调用接口。
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
def fast_throttle(monkeypatch):
    """去掉接口节流等待，避免测试变慢"""
    from nonebot_plugin_larkuser.group import client

    monkeypatch.setattr(client._info_throttle, "_min_interval", 0.0)
    monkeypatch.setattr(client._members_throttle, "_min_interval", 0.0)


@pytest.fixture
async def db(monkeypatch):
    """把缓存模块的数据库会话替换为临时内存数据库"""
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.models import QQGroupInfo

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(QQGroupInfo.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(cache, "get_session", lambda **_: factory())
    yield factory
    await engine.dispose()


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.self_id = "bot-1"
    return bot


class _FakeAdapter:
    """只返回固定响应的 QQ 适配器替身"""

    def __init__(self, response) -> None:
        self.response = response
        self.requests = []

    def get_api_base(self):
        from nonebot.drivers import URL

        return URL("https://api.sgroup.qq.com")

    async def request(self, request):
        self.requests.append(request)
        return self.response


class _FakeQQBot:
    """最小化的 QQ 官方 Bot 替身"""

    def __init__(self, response) -> None:
        self.adapter = _FakeAdapter(response)
        self.self_id = "bot-1"

    async def get_authorization_header(self) -> dict[str, str]:
        return {"Authorization": "QQBot test-token"}


def _json_response(payload, status_code: int = 200):
    from nonebot.drivers import Response

    return Response(status_code, content=json.dumps(payload).encode())


# ── 接口解析 ──


def test_parse_group_member_converts_joined_at_to_utc_naive() -> None:
    from nonebot_plugin_larkuser.group.client import parse_group_member

    member = parse_group_member(
        {
            "member_openid": "openid-1",
            "username": "阳光小助手",
            "member_role": "admin",
            "bot": False,
            "joined_at": "2025-08-20T09:15:00+08:00",
            "union_openid": "union-1",
        },
    )
    assert member.member_openid == "openid-1"
    assert member.nickname == "阳光小助手"
    assert member.role == "admin"
    assert member.is_bot is False
    assert member.union_openid == "union-1"
    assert member.joined_at == datetime(2025, 8, 20, 1, 15)


def test_parse_group_member_tolerates_unknown_role_and_time() -> None:
    from nonebot_plugin_larkuser.group.client import parse_group_member

    member = parse_group_member({"member_openid": "openid-2", "member_role": "stranger", "joined_at": "not-a-time"})
    assert member.role == "member"
    assert member.joined_at is None
    assert member.nickname == ""


@pytest.mark.asyncio
async def test_fetch_group_members_page_parses_response() -> None:
    from nonebot_plugin_larkuser.group.client import fetch_group_members_page

    bot = _FakeQQBot(
        _json_response(
            {
                "members": [
                    {"member_openid": "a1", "username": "AAA", "member_role": "member", "bot": False},
                    {"member_openid": "", "username": "缺少 openid 的脏数据"},
                ],
                "next_cursor": "cursor-2",
            },
        ),
    )
    members, next_cursor = await fetch_group_members_page(bot, "group-openid", "cursor-1")
    assert [member.member_openid for member in members] == ["a1"]
    assert next_cursor == "cursor-2"
    request = bot.adapter.requests[0]
    assert request.method == "GET"
    assert str(request.url).startswith("https://api.sgroup.qq.com/v2/groups/group-openid/members")
    assert request.url.query.get("cursor") == "cursor-1"
    assert request.headers["Authorization"] == "QQBot test-token"


@pytest.mark.asyncio
async def test_fetch_group_info_maps_fields() -> None:
    from nonebot_plugin_larkuser.group.client import fetch_group_info

    bot = _FakeQQBot(
        _json_response(
            {
                "group_openid": "group-openid",
                "group_name": "读书分享会",
                "group_finger_memo": "每周共读一本好书",
                "group_member_num": 256,
            },
        ),
    )
    info = await fetch_group_info(bot, "group-openid")
    assert (info.group_name, info.description, info.member_count) == ("读书分享会", "每周共读一本好书", 256)
    assert str(bot.adapter.requests[0].url).endswith("/v2/groups/group-openid/info")


@pytest.mark.asyncio
async def test_fetch_all_group_members_follows_cursor(monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import client
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo

    pages = {
        "": ([QQGroupMemberInfo(member_openid="a1")], "cursor-1"),
        "cursor-1": ([QQGroupMemberInfo(member_openid="a2")], ""),
    }

    async def fake_page(bot, group_openid, cursor=""):
        return pages[cursor]

    monkeypatch.setattr(client, "fetch_group_members_page", fake_page)
    members = await client.fetch_all_group_members(_bot(), "group-openid", max_members=100)
    assert [member.member_openid for member in members] == ["a1", "a2"]


@pytest.mark.asyncio
async def test_fetch_all_group_members_stops_on_looping_cursor(monkeypatch) -> None:
    """接口一直返回同一个游标时不会无限翻页"""
    from nonebot_plugin_larkuser.group import client
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo

    calls = 0

    async def fake_page(bot, group_openid, cursor=""):
        nonlocal calls
        calls += 1
        return [QQGroupMemberInfo(member_openid=f"member-{calls}")], "same-cursor"

    monkeypatch.setattr(client, "fetch_group_members_page", fake_page)
    members = await client.fetch_all_group_members(_bot(), "group-openid", max_members=100)
    assert calls == 2
    assert len(members) == 2


@pytest.mark.asyncio
async def test_fetch_all_group_members_respects_max_members(monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import client
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo

    counter = iter(range(1000))

    async def fake_page(bot, group_openid, cursor=""):
        return [QQGroupMemberInfo(member_openid=f"member-{next(counter)}")], f"cursor-{next(counter)}"

    monkeypatch.setattr(client, "fetch_group_members_page", fake_page)
    members = await client.fetch_all_group_members(_bot(), "group-openid", max_members=3)
    assert len(members) == 3


@pytest.mark.asyncio
async def test_fetch_group_info_maps_permission_error() -> None:
    from nonebot_plugin_larkuser.group.client import QQGroupPermissionError, fetch_group_info

    bot = _FakeQQBot(_json_response({"code": 11253, "message": "应用无接口访问权限"}, status_code=403))
    with pytest.raises(QQGroupPermissionError) as exc_info:
        await fetch_group_info(bot, "group-openid")
    assert exc_info.value.code == 11253


@pytest.mark.asyncio
async def test_fetch_group_members_maps_rate_limit() -> None:
    from nonebot.drivers import Response
    from nonebot_plugin_larkuser.group.client import QQGroupRateLimitError, fetch_group_members_page

    bot = _FakeQQBot(Response(429, content=b""))
    with pytest.raises(QQGroupRateLimitError):
        await fetch_group_members_page(bot, "group-openid")


@pytest.mark.asyncio
async def test_fetch_group_members_maps_other_errors() -> None:
    from nonebot_plugin_larkuser.group.client import QQGroupAPIError, fetch_group_members_page

    bot = _FakeQQBot(_json_response({"code": 10001, "message": "内部错误"}, status_code=500))
    with pytest.raises(QQGroupAPIError) as exc_info:
        await fetch_group_members_page(bot, "group-openid")
    assert exc_info.value.code == 10001


# ── 昵称补全 ──


@pytest.mark.asyncio
async def test_fill_user_nicknames_creates_guest_user(db) -> None:
    from nonebot_plugin_larkuser.group.cache import fill_user_nicknames
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo
    from nonebot_plugin_larkuser.models import GuestUser

    updated = await fill_user_nicknames(
        [
            QQGroupMemberInfo(member_openid="guest-1", nickname="阳光小助手"),
            QQGroupMemberInfo(member_openid="bot-1", nickname="Moonlark", is_bot=True),
        ],
    )
    assert updated == 1
    async with db() as session:
        assert (await session.get(GuestUser, "guest-1")).nickname == "阳光小助手"
        assert await session.get(GuestUser, "bot-1") is None


@pytest.mark.asyncio
async def test_fill_user_nicknames_updates_changed_guest_nickname(db) -> None:
    from nonebot_plugin_larkuser.group.cache import fill_user_nicknames
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo
    from nonebot_plugin_larkuser.models import GuestUser

    async with db() as session:
        session.add(GuestUser(user_id="guest-1", nickname="旧昵称"))
        await session.commit()

    await fill_user_nicknames([QQGroupMemberInfo(member_openid="guest-1", nickname="新昵称")])
    async with db() as session:
        assert (await session.get(GuestUser, "guest-1")).nickname == "新昵称"


@pytest.mark.asyncio
async def test_fill_user_nicknames_fills_empty_registered_nickname(db) -> None:
    from nonebot_plugin_larkuser.group.cache import NICK_SOURCE_GROUP_MEMBER, NICK_SOURCE_KEY, fill_user_nicknames
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo
    from nonebot_plugin_larkuser.models import UserData

    async with db() as session:
        session.add(UserData(user_id="user-1", nickname="", register_time=datetime.now(), config="{}"))
        await session.commit()

    assert await fill_user_nicknames([QQGroupMemberInfo(member_openid="user-1", nickname="已注册用户")]) == 1
    async with db() as session:
        user = await session.get(UserData, "user-1")
        assert user.nickname == "已注册用户"
        assert json.loads(user.config)[NICK_SOURCE_KEY] == NICK_SOURCE_GROUP_MEMBER


@pytest.mark.asyncio
async def test_fill_user_nicknames_keeps_user_set_nickname(db) -> None:
    from nonebot_plugin_larkuser.group.cache import fill_user_nicknames
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo
    from nonebot_plugin_larkuser.models import GuestUser, UserData

    async with db() as session:
        session.add(UserData(user_id="user-1", nickname="我自己设置的昵称", register_time=datetime.now(), config="{}"))
        await session.commit()

    assert await fill_user_nicknames([QQGroupMemberInfo(member_openid="user-1", nickname="QQ 昵称")]) == 0
    async with db() as session:
        assert (await session.get(UserData, "user-1")).nickname == "我自己设置的昵称"
        assert await session.get(GuestUser, "user-1") is None


# ── 缓存读写 ──


@pytest.mark.asyncio
async def test_refresh_group_members_stores_and_prunes(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo

    async def first_sync(bot, group_openid, *, max_members):
        return [
            QQGroupMemberInfo(member_openid="a1", nickname="AAA", role="owner"),
            QQGroupMemberInfo(member_openid="a2", nickname="BBB"),
        ]

    monkeypatch.setattr(cache, "fetch_all_group_members", first_sync)
    await cache.refresh_group_members(_bot(), "group-openid")
    members = await cache.get_cached_group_members("group-openid")
    assert {member.member_openid for member in members} == {"a1", "a2"}
    assert (await cache.get_group_member("group-openid", "a1")).role == "owner"

    async def second_sync(bot, group_openid, *, max_members):
        return [QQGroupMemberInfo(member_openid="a2", nickname="BBB-新")]

    monkeypatch.setattr(cache, "fetch_all_group_members", second_sync)
    await cache.refresh_group_members(_bot(), "group-openid")
    members = await cache.get_cached_group_members("group-openid")
    assert [member.member_openid for member in members] == ["a2"]
    assert members[0].nickname == "BBB-新"


@pytest.mark.asyncio
async def test_refresh_group_members_keeps_cache_on_api_error(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.group.client import QQGroupPermissionError
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo

    async def ok(bot, group_openid, *, max_members):
        return [QQGroupMemberInfo(member_openid="a1", nickname="AAA")]

    monkeypatch.setattr(cache, "fetch_all_group_members", ok)
    await cache.refresh_group_members(_bot(), "group-openid")

    async def denied(bot, group_openid, *, max_members):
        raise QQGroupPermissionError("无权限", code=11253)

    monkeypatch.setattr(cache, "fetch_all_group_members", denied)
    members = await cache.refresh_group_members(_bot(), "group-openid")
    assert [member.member_openid for member in members] == ["a1"]


@pytest.mark.asyncio
async def test_get_group_member_nickname_map_prefers_moonlark_nickname(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.group.types import QQGroupMemberInfo
    from nonebot_plugin_larkuser.models import GuestUser, UserData

    async with db() as session:
        session.add(UserData(user_id="a1", nickname="自设昵称", register_time=datetime.now(), config="{}"))
        await session.commit()

    async def sync(bot, group_openid, *, max_members):
        return [
            QQGroupMemberInfo(member_openid="a1", nickname="QQ 上的昵称"),
            QQGroupMemberInfo(member_openid="a2", nickname="只有 QQ 昵称"),
            QQGroupMemberInfo(member_openid="a3", nickname=""),
        ]

    monkeypatch.setattr(cache, "fetch_all_group_members", sync)
    await cache.refresh_group_members(_bot(), "group-openid")

    # 已注册用户保留自己的昵称；未注册用户使用群成员列表里的昵称
    async with db() as session:
        assert (await session.get(UserData, "a1")).nickname == "自设昵称"
        assert (await session.get(GuestUser, "a2")).nickname == "只有 QQ 昵称"
        assert await session.get(GuestUser, "a3") is None

    assert await cache.get_group_member_nickname_map("group-openid") == {
        "自设昵称": "a1",
        "只有 QQ 昵称": "a2",
    }


@pytest.mark.asyncio
async def test_get_group_member_nickname_map_is_empty_without_cache(db) -> None:
    from nonebot_plugin_larkuser.group import cache

    assert await cache.get_group_member_nickname_map("unknown-group") == {}


@pytest.mark.asyncio
async def test_get_group_name_uses_cache(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.group.types import QQGroupInfo

    async def sync_info(bot, group_openid):
        return QQGroupInfo(group_openid=group_openid, group_name="读书分享会", member_count=3)

    monkeypatch.setattr(cache, "fetch_group_info", sync_info)
    assert await cache.refresh_group_info(_bot(), "group-openid") is not None
    assert await cache.get_group_name(_bot(), "group-openid") == "读书分享会"

    async def unexpected(*args, **kwargs):
        raise AssertionError("缓存未过期时不应调用接口")

    monkeypatch.setattr(cache, "fetch_group_info", unexpected)
    assert await cache.get_group_name(_bot(), "group-openid") == "读书分享会"


@pytest.mark.asyncio
async def test_get_group_name_refreshes_when_cache_expired(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.group.types import QQGroupInfo
    from nonebot_plugin_larkuser.models import QQGroupInfo as QQGroupInfoModel

    async with db() as session:
        session.add(
            QQGroupInfoModel(
                group_openid="group-openid",
                group_name="旧群名",
                info_updated_at=datetime.now() - timedelta(days=7),
            ),
        )
        await session.commit()

    async def sync_info(bot, group_openid):
        return QQGroupInfo(group_openid=group_openid, group_name="新群名")

    monkeypatch.setattr(cache, "fetch_group_info", sync_info)
    assert await cache.get_group_name(_bot(), "group-openid") == "新群名"


@pytest.mark.asyncio
async def test_refresh_group_info_records_error(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.group.client import QQGroupPermissionError
    from nonebot_plugin_larkuser.models import QQGroupInfo

    async def denied(bot, group_openid):
        raise QQGroupPermissionError("应用没有该群接口的访问权限（11253）", code=11253)

    monkeypatch.setattr(cache, "fetch_group_info", denied)
    assert await cache.refresh_group_info(_bot(), "group-openid") is None
    async with db() as session:
        record = await session.get(QQGroupInfo, {"group_openid": "group-openid"})
        assert "11253" in record.last_error
        assert record.info_updated_at is not None


@pytest.mark.asyncio
async def test_sync_all_groups_skips_fresh_cache(db, monkeypatch) -> None:
    from nonebot_plugin_larkuser.group import cache
    from nonebot_plugin_larkuser.models import QQGroupInfo

    async with db() as session:
        session.add(QQGroupInfo(group_openid="fresh-group", bot_id="bot-1", members_synced_at=datetime.now()))
        await session.commit()

    async def unexpected(*args, **kwargs):
        raise AssertionError("缓存新鲜时不应触发同步")

    monkeypatch.setattr(cache, "refresh_group_members", unexpected)
    await cache.sync_all_groups()
