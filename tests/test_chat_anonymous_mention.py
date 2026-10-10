"""chat 发送消息时把上下文中出现过的匿名用户提及解析为 At

匿名用户（未设置昵称）在上下文里以默认名 ``匿名-XXXX``（主账号 ID 末 4 位）出现，
模型回复时可能直接写出 ``匿名-XXXX`` 或裸的 ``XXXX``，发送前需要还原成对真实用户的
At，避免提醒不到要提及的人。
"""

from datetime import datetime
from typing import Any, Optional

import pytest


def make_cached_message(nickname: str, user_id: str, platform_user_id: str = "") -> Any:
    """构造 CachedMessage 测试桩"""
    return {
        "content": "hello",
        "nickname": nickname,
        "send_time": datetime.now(),
        "user_id": user_id,
        "platform_user_id": platform_user_id or user_id,
        "self": False,
        "message_id": "0",
        "images": [],
        "to_me": False,
        "triggered_reply": False,
    }


def make_group_session(monkeypatch: pytest.MonkeyPatch, cached_messages: list, group_users: dict) -> Any:
    """创建一个绕过初始化的 GroupSession，注入消息缓存与群成员昵称映射"""
    from nonebot_plugin_chat.core.session.group import GroupSession

    session = GroupSession.__new__(GroupSession)

    def _cached_messages(_self) -> list:
        return cached_messages

    monkeypatch.setattr(GroupSession, "cached_messages", property(_cached_messages))
    session.group_users = group_users

    # 直接返回群成员映射，绕开需要真实 bot 连接的成员列表刷新
    async def get_users() -> dict[str, str]:
        return group_users

    session.get_users = get_users  # type: ignore[method-assign]
    return session


def segments_of(message: Any) -> list[tuple[str, Optional[str]]]:
    """把 UniMessage 简化为 (类型, 内容或目标) 列表，便于断言"""
    result = []
    for segment in message:
        if segment.__class__.__name__ == "At":
            result.append(("At", segment.target))
        else:
            result.append(("Text", getattr(segment, "text", None)))
    return result


async def test_full_anonymous_name_is_parsed_as_at(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.core.session.base import get_anonymous_default_nickname

    cached_messages = [make_cached_message(get_anonymous_default_nickname("1234"), "1234", "1234")]
    session = make_group_session(monkeypatch, cached_messages, {})
    message = await session.format_message("匿名-1234 你怎么看？")
    assert segments_of(message) == [("At", "1234"), ("Text", " 你怎么看？")]


async def test_bare_suffix_is_parsed_as_at(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.core.session.base import get_anonymous_default_nickname

    cached_messages = [make_cached_message(get_anonymous_default_nickname("1234"), "1234", "1234")]
    session = make_group_session(monkeypatch, cached_messages, {})
    message = await session.format_message("喂，1234，别跑")
    assert segments_of(message) == [("Text", "喂，"), ("At", "1234"), ("Text", "，别跑")]


async def test_at_prefixed_full_name_consumes_the_at_sign(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.core.session.base import get_anonymous_default_nickname

    cached_messages = [make_cached_message(get_anonymous_default_nickname("1234"), "1234", "1234")]
    session = make_group_session(monkeypatch, cached_messages, {})
    message = await session.format_message("@匿名-1234 说的什么意思？")
    assert segments_of(message) == [("At", "1234"), ("Text", " 说的什么意思？")]


async def test_bare_suffix_inside_longer_number_is_not_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.core.session.base import get_anonymous_default_nickname

    cached_messages = [make_cached_message(get_anonymous_default_nickname("1234"), "1234", "1234")]
    session = make_group_session(monkeypatch, cached_messages, {})
    message = await session.format_message("现在是 123456，编号 id-1234")
    assert segments_of(message) == [("Text", "现在是 123456，编号 id-1234")]


async def test_named_nickname_is_not_parsed_as_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    """有昵称的用户不属于匿名用户，裸的 4 位数字也不会被替换"""
    cached_messages = [
        make_cached_message("小张", "1234", "1234"),
        make_cached_message("小李", "9999", "9999"),
    ]
    session = make_group_session(monkeypatch, cached_messages, {"小张": "1234", "小李": "9999"})
    message = await session.format_message("现在是 1234")
    assert segments_of(message) == [("Text", "现在是 1234")]


async def test_unknown_anonymous_suffix_stays_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """未在上下文中出现过的匿名后缀不会被解析"""
    cached_messages = [make_cached_message("小张", "1234", "1234")]
    session = make_group_session(monkeypatch, cached_messages, {"小张": "1234"})
    message = await session.format_message("匿名-9999 是谁呀")
    assert segments_of(message) == [("Text", "匿名-9999 是谁呀")]


async def test_multiple_anonymous_users_and_existing_at_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.core.session.base import get_anonymous_default_nickname

    cached_messages = [
        make_cached_message("小明", "1111", "1111"),
        make_cached_message(get_anonymous_default_nickname("1234"), "1234", "1234"),
        make_cached_message(get_anonymous_default_nickname("abcd5678"), "abcd5678", "openid_abcd5678"),
    ]
    session = make_group_session(monkeypatch, cached_messages, {"小明": "1111"})
    message = await session.format_message("@小明 @匿名-1234 5678 也要参加 @Anonymous")
    assert segments_of(message) == [
        ("At", "1111"),
        ("Text", " "),
        ("At", "1234"),
        ("Text", " "),
        ("At", "openid_abcd5678"),
        ("Text", " 也要参加 @Anonymous"),
    ]


async def test_anonymous_users_collection_skips_self_and_named_users(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.core.session.base import get_anonymous_default_nickname

    cached_messages = [
        make_cached_message("小明", "1111", "1111"),
        make_cached_message(get_anonymous_default_nickname("1234"), "1234", "1234"),
    ]
    self_message = make_cached_message("Moonlark", "", "")
    self_message["self"] = True
    cached_messages.append(self_message)
    # platform_user_id 缺失时回退到主账号 ID
    fallback = make_cached_message(get_anonymous_default_nickname("5678"), "5678", "")
    fallback["platform_user_id"] = ""
    cached_messages.append(fallback)

    session = make_group_session(monkeypatch, cached_messages, {})
    assert session._get_anonymous_users() == {"1234": "1234", "5678": "5678"}


async def test_format_message_without_users_returns_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    session = make_group_session(monkeypatch, [], {})
    message = await session.format_message("没有已知成员时保持原样")
    assert segments_of(message) == [("Text", "没有已知成员时保持原样")]
