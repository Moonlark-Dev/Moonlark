"""nonebot_plugin_buff 效果（Buff）系统回归测试。

覆盖：注册表查询、时间维度、次数维度、两个维度共存、多层叠加（支持 / 不支持）
以及霉运内置 buff 的收益系数。
"""

from datetime import timedelta

import pytest


@pytest.mark.asyncio
async def test_register_and_lookup_definition() -> None:
    from nonebot_plugin_buff.registry import (
        BuffDefinition,
        get_buff_definition,
        get_buff_definitions,
        register_buff,
    )

    definition = register_buff(BuffDefinition(id="test:single", name_key="builtin.bad_luck.name", max_layers=1))
    assert get_buff_definition("test:single") is definition
    assert not definition.stackable
    assert "test:single" in get_buff_definitions()

    assert get_buff_definition("test:unknown") is None


@pytest.mark.asyncio
async def test_attach_non_stackable_refreshes() -> None:
    from nonebot_plugin_buff.api import attach_buff, get_buff_attachment
    from nonebot_plugin_buff.registry import BuffDefinition, register_buff

    register_buff(BuffDefinition(id="test:plain", name_key="builtin.bad_luck.name", max_layers=1))
    user_id = "buff-test-plain"

    first = await attach_buff(user_id, "test:plain", duration=timedelta(hours=1))
    assert first.layers == 1

    second = await attach_buff(user_id, "test:plain", duration=timedelta(hours=2))
    # 不支持叠加的 buff 重新附着只是刷新，层数保持 1，到期时间被重置
    assert second.layers == 1
    assert second.expires_at is not None and first.expires_at is not None
    assert second.expires_at > first.expires_at

    attachment = await get_buff_attachment(user_id, "test:plain")
    assert attachment is not None
    assert attachment.layers == 1


@pytest.mark.asyncio
async def test_attach_stackable_caps_layers() -> None:
    from nonebot_plugin_buff.api import attach_buff, get_buff_layers, has_buff
    from nonebot_plugin_buff.registry import BuffDefinition, register_buff

    register_buff(BuffDefinition(id="test:stack", name_key="builtin.bad_luck.name", max_layers=3))
    user_id = "buff-test-stack"

    await attach_buff(user_id, "test:stack", duration=timedelta(hours=1))
    assert await get_buff_layers(user_id, "test:stack") == 1

    await attach_buff(user_id, "test:stack", duration=timedelta(hours=1), layers=2)
    # 层数被限制在 max_layers
    assert await get_buff_layers(user_id, "test:stack") == 3
    assert await has_buff(user_id, "test:stack")


@pytest.mark.asyncio
async def test_time_dimension_expires() -> None:
    from nonebot_plugin_buff.api import attach_buff, get_buff_attachments, has_buff

    user_id = "buff-test-time"
    await attach_buff(user_id, "test:plain", duration=timedelta(seconds=-1))

    # 已超时的附着在读取时会被清理
    assert not await has_buff(user_id, "test:plain")
    assert await get_buff_attachments(user_id) == []


@pytest.mark.asyncio
async def test_count_dimension_consumes() -> None:
    from nonebot_plugin_buff.api import attach_buff, consume_buff, get_buff_attachment, has_buff

    user_id = "buff-test-count"
    await attach_buff(user_id, "test:count", count=2)

    assert await consume_buff(user_id, "test:count")
    attachment = await get_buff_attachment(user_id, "test:count")
    assert attachment is not None and attachment.remaining_count == 1

    assert await consume_buff(user_id, "test:count")
    # 次数耗尽后整个 buff 消失
    assert not await has_buff(user_id, "test:count")
    assert not await consume_buff(user_id, "test:count")


@pytest.mark.asyncio
async def test_time_and_count_dimensions_together() -> None:
    from nonebot_plugin_buff.api import attach_buff, consume_buff, has_buff

    user_id = "buff-test-both"
    await attach_buff(user_id, "test:both", duration=timedelta(hours=2), count=1)

    attachment = await consume_buff(user_id, "test:both")
    assert attachment
    # 次数先耗尽：即使时间还没到，buff 也会消失
    assert not await has_buff(user_id, "test:both")


@pytest.mark.asyncio
async def test_no_count_limit_is_not_consumed() -> None:
    from nonebot_plugin_buff.api import attach_buff, consume_buff, get_buff_attachment

    user_id = "buff-test-unlimited"
    await attach_buff(user_id, "test:unlimited", duration=timedelta(hours=1))

    assert await consume_buff(user_id, "test:unlimited")
    attachment = await get_buff_attachment(user_id, "test:unlimited")
    assert attachment is not None
    assert attachment.remaining_count is None


@pytest.mark.asyncio
async def test_detach_and_clear() -> None:
    from nonebot_plugin_buff.api import attach_buff, clear_buffs, detach_buff, get_buff_attachments

    user_id = "buff-test-detach"
    await attach_buff(user_id, "test:stack", layers=3, duration=timedelta(hours=1))
    assert await detach_buff(user_id, "test:stack", layers=1)
    attachments = await get_buff_attachments(user_id)
    assert len(attachments) == 1 and attachments[0].layers == 2

    await attach_buff(user_id, "test:plain", duration=timedelta(hours=1))
    assert await clear_buffs(user_id) == 2
    assert await get_buff_attachments(user_id) == []


@pytest.mark.asyncio
async def test_bad_luck_multiplier() -> None:
    from nonebot_plugin_buff.builtin import (
        BAD_LUCK_BUFF_ID,
        BAD_LUCK_DURATION,
        BAD_LUCK_MAX_LAYERS,
        attach_bad_luck,
        bad_luck_multiplier,
        get_bad_luck_layers,
        get_bad_luck_multiplier,
    )
    from nonebot_plugin_buff.registry import get_buff_definition

    assert BAD_LUCK_DURATION == timedelta(hours=2)
    assert BAD_LUCK_MAX_LAYERS == 3
    definition = get_buff_definition(BAD_LUCK_BUFF_ID)
    assert definition is not None and definition.stackable

    assert bad_luck_multiplier(0) == 1.0
    assert bad_luck_multiplier(1) == 0.5
    assert bad_luck_multiplier(3) == 0.125

    user_id = "buff-test-bad-luck"
    assert await get_bad_luck_multiplier(user_id) == 1.0

    await attach_bad_luck(user_id, layers=2)
    assert await get_bad_luck_layers(user_id) == 2
    assert await get_bad_luck_multiplier(user_id) == 0.25


@pytest.mark.asyncio
async def test_unknown_buff_gets_placeholder_definition() -> None:
    from nonebot_plugin_buff.registry import ensure_buff_definition

    definition = ensure_buff_definition("test:never-registered")
    assert definition.max_layers == 1
    assert definition.name_key == "test:never-registered"
