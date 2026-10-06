"""权限表内存缓存（nonebot_plugin_access.utils.cache）的回归测试。

覆盖：启动/定时刷新整表、写入后立即刷新、权限检查不再查库、
以及 access reload 子命令的路由与权限。
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

CACHE_GET_SESSION = "nonebot_plugin_access.utils.cache.get_session"
SET_ACCESS_GET_SESSION = "nonebot_plugin_access.utils.set_access.get_session"


async def _make_engine() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """建一张临时权限表（sqlite 内存库），返回引擎与会话工厂。"""
    from nonebot_plugin_access.models import SubjectData

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SubjectData.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _patch_session(factory: async_sessionmaker[AsyncSession], target: str = CACHE_GET_SESSION):
    """把目标模块的 get_session 指向临时库，每次调用返回新会话。"""
    return patch(target, side_effect=lambda **_: factory())


async def _add_rows(engine: AsyncEngine, rows: list[tuple[str, str, bool]]) -> None:
    from nonebot_plugin_access.models import SubjectData

    async with AsyncSession(engine) as session:
        session.add_all(
            [SubjectData(subject=subject, name=name, available=available) for subject, name, available in rows]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_reload_builds_permission_table() -> None:
    """reload 拉取整张权限表；重复记录按 all() 聚合，缺失记录沿用默认放行。"""
    from nonebot_plugin_access.utils.cache import access_cache

    engine, factory = await _make_engine()
    await _add_rows(
        engine,
        [
            ("u1", "all", False),
            ("u1", "plugin_sign", True),
            ("u1", "plugin_sign", False),
            ("group_g1", "all", False),
        ],
    )
    with _patch_session(factory):
        assert await access_cache.reload() == 4

    assert access_cache.loaded
    assert access_cache.get("u1", "all") is False
    # 同一 (subject, name) 有多条记录时与改动前的 all() 语义一致
    assert access_cache.get("u1", "plugin_sign") is False
    assert access_cache.get("group_g1", "all") is False
    assert access_cache.get("u1", "plugin_jrrp") is True
    assert access_cache.get("nobody", "all") is True
    assert access_cache.permissions_of("u1") == {"all": False, "plugin_sign": False}
    assert access_cache.permissions_of("nobody") == {}

    await engine.dispose()


@pytest.mark.asyncio
async def test_reload_picks_up_external_changes() -> None:
    """重新拉取（定时刷新）能反映数据库里的新增与删除。"""
    from nonebot_plugin_access.models import SubjectData
    from nonebot_plugin_access.utils.cache import access_cache

    engine, factory = await _make_engine()
    with _patch_session(factory):
        await access_cache.reload()
        assert access_cache.get("u1", "all") is True

        await _add_rows(engine, [("u1", "all", False)])
        await access_cache.reload()
        assert access_cache.get("u1", "all") is False

        async with AsyncSession(engine) as session:
            row = await session.scalar(select(SubjectData).where(SubjectData.subject == "u1"))
            assert row is not None
            await session.delete(row)
            await session.commit()

        await access_cache.reload()
        assert access_cache.get("u1", "all") is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_is_available_reads_cache_without_database() -> None:
    """权限表加载后，权限检查只读内存缓存，不再访问数据库。"""
    from nonebot_plugin_access.utils import cache as cache_module
    from nonebot_plugin_access.utils.checker import is_available

    engine, factory = await _make_engine()
    await _add_rows(engine, [("u1", "all", False)])
    with _patch_session(factory):
        await cache_module.access_cache.reload()

    with patch(CACHE_GET_SESSION, side_effect=AssertionError("权限检查不应访问数据库")):
        assert await is_available("u1", "all") is False
        assert await is_available("u1", "plugin_jrrp") is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_set_access_updates_database_and_cache() -> None:
    """access ban/pardon 等写入后，数据库与缓存同时更新。"""
    from nonebot_plugin_access.models import SubjectData
    from nonebot_plugin_access.utils.cache import access_cache
    from nonebot_plugin_access.utils.set_access import set_access

    engine, factory = await _make_engine()
    with _patch_session(factory), _patch_session(factory, SET_ACCESS_GET_SESSION):
        await access_cache.reload()
        await set_access("u1", "all", False)
        assert access_cache.get("u1", "all") is False
        async with AsyncSession(engine) as session:
            assert await session.scalar(select(SubjectData.available).where(SubjectData.subject == "u1")) is False

        await set_access("u1", "all", True)
        assert access_cache.get("u1", "all") is True
        async with AsyncSession(engine) as session:
            assert await session.scalar(select(SubjectData.available).where(SubjectData.subject == "u1")) is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_web_permissions_reads_cache() -> None:
    """web 权限接口与权限检查共用缓存。"""
    from nonebot_plugin_access import web as web_module

    class _FakeCache:
        def __init__(self) -> None:
            self.loaded = False

        async def ensure_loaded(self) -> None:
            self.loaded = True

        def permissions_of(self, subject: str) -> dict[str, bool]:
            assert subject == "u1"
            return {"all": False}

    fake_cache = _FakeCache()
    with patch.object(web_module, "access_cache", fake_cache):
        assert await web_module._(None, "u1") == {"all": False}
    assert fake_cache.loaded


@pytest.mark.asyncio
async def test_reload_subcommand_routes_and_requires_superuser() -> None:
    """access reload 命中 reload 子命令（无需主体），且整条命令仅 SUPERUSER 可用。"""
    from nonebot import get_driver
    from nonebot_plugin_access.__main__ import access_command

    prefix = next(iter(get_driver().config.command_start or ["/"]))
    command = access_command.command()

    result = command.parse(f"{prefix}access reload")
    assert result.matched
    assert "reload" in result.subcommands
    assert "subject" not in result.all_matched_args

    # 主体参数移到各子命令后，原有指令的解析结果不变
    result = command.parse(f"{prefix}access ban 12345")
    assert result.matched
    assert "ban" in result.subcommands
    assert result.all_matched_args["subject"] == "12345"

    result = command.parse(f"{prefix}access block all 12345")
    assert result.matched
    assert "block" in result.subcommands
    assert result.all_matched_args["access"] == "all"
    assert result.all_matched_args["subject"] == "12345"

    # 整条命令（含 reload 子命令）的权限就是 SUPERUSER
    # （on_alconna 会把传入的 permission 包装成 Permission() | permission）
    from nonebot.permission import SUPERUSER

    assert {type(checker.call) for checker in access_command.permission.checkers} == {
        type(checker.call) for checker in SUPERUSER.checkers
    }
