"""waifu 群成员数量下限的回归测试。

覆盖点：

- 群成员少于 3 人（或群成员列表获取失败）时不再进行匹配，也不再显示「没有老婆」，
  而是给出「活跃成员不足或获取失败」的提示；
- 群成员足够时保持原有匹配流程。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_has_enough_members() -> None:
    from nonebot_plugin_everyday_wife.utils.init import MIN_GROUP_MEMBERS_FOR_MATCH, has_enough_members

    assert MIN_GROUP_MEMBERS_FOR_MATCH == 3
    assert not has_enough_members([])
    assert not has_enough_members(["m1", "m2"])
    assert has_enough_members(["m1", "m2", "m3"])


async def _run_waifu(monkeypatch, members: list[str]) -> list[str]:
    """以最小 mock 跑一次 waifu 处理器，返回它调用 lang.finish 的 key 列表"""
    import nonebot_plugin_everyday_wife.__main__ as module
    from nonebot.exception import FinishedException

    finished: list[str] = []

    async def fake_finish(key, user_id, *args, **kwargs):
        finished.append(key)
        raise FinishedException

    monkeypatch.setattr(module.lang, "finish", fake_finish)

    async def fake_members(bot, group_id):
        return members

    monkeypatch.setattr(module, "get_group_members", fake_members)
    matched = AsyncMock(return_value=None)
    monkeypatch.setattr(module, "match_user_with_available", matched)

    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    event = MagicMock()
    event.get_user_id.return_value = "caller-openid"
    arg_message = MagicMock()
    arg_message.extract_plain_text.return_value = ""

    with pytest.raises(FinishedException):
        await module._(
            MagicMock(),
            event,
            session,
            MagicMock(),
            "main-user",
            "group-openid",
            "qq_group-openid",
            arg_message,
            is_c2c=False,
        )
    return finished


@pytest.mark.asyncio
async def test_waifu_refuses_to_match_small_group(monkeypatch) -> None:
    import nonebot_plugin_everyday_wife.__main__ as module

    finished = await _run_waifu(monkeypatch, ["m1", "m2"])
    assert finished == ["not_enough_members"]
    module.match_user_with_available.assert_not_awaited()


@pytest.mark.asyncio
async def test_waifu_refuses_to_match_when_member_list_empty(monkeypatch) -> None:
    finished = await _run_waifu(monkeypatch, [])
    assert finished == ["not_enough_members"]


@pytest.mark.asyncio
async def test_waifu_matches_when_group_is_large_enough(monkeypatch) -> None:
    import nonebot_plugin_everyday_wife.__main__ as module

    finished = await _run_waifu(monkeypatch, ["m1", "m2", "m3"])
    # 群成员数量达标后仍走原有匹配流程；没有可用对象时才是「没有老婆」
    assert finished == ["unmatched"]
    module.match_user_with_available.assert_awaited_once()
