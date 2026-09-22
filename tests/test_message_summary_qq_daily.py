"""nonebot_plugin_message_summary 每日总结在 QQ 适配器下的回归测试。

覆盖点：

- 群内只剩 QQ 适配器 Bot 可用时，6:00 之后由第一条消息触发总结的生成与发送；
- 每个群每天只推送一次；
- 6:00 之前、未开启每日总结、群里仍有可用 OneBot bot、当天已推送时都不触发；
- group-daily 指令消息让位给指令处理器，避免同一条消息推送两次；
- 已绑定 OneBot 群号的群用群号统一推送状态，避免两条链路各推送一次；
- OB11 定时推送只使用 OneBot V11 bot。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def qq_daily_env(monkeypatch, tmp_path):
    """把配置 / 状态文件指向临时目录，并把「是否已过 6:00」变为确定条件"""
    import nonebot_plugin_message_summary.__main__ as module
    from nonebot_plugin_larkutils.file import FileManager

    enabled = FileManager(tmp_path / "everyday_summary_config.json", [])
    state = FileManager(tmp_path / "daily_summary_state.json", {})
    monkeypatch.setattr(module, "get_everyday_summary_config", lambda: enabled)
    monkeypatch.setattr(module, "get_daily_summary_state", lambda: state)
    monkeypatch.setattr(module, "get_command_prefix", lambda: ".")
    # 0 / 24 分别模拟「已过 6:00」与「未到 6:00」，避免测试结果受运行时刻影响
    monkeypatch.setattr(module, "DAILY_SUMMARY_HOUR", 0)
    module._qq_daily_summary_pending.clear()
    return module, enabled, state


@pytest.fixture
def stub_summary(monkeypatch):
    """替换 AI 生成与图片渲染，避免测试访问网络"""
    import nonebot_plugin_message_summary.__main__ as module

    generate = AsyncMock(return_value="# 今日总结")
    monkeypatch.setattr(module, "generate_daily_summary", generate)
    monkeypatch.setattr(module, "md_to_pic", AsyncMock(return_value=b"image-bytes"))
    return generate


@pytest.fixture
def sent_messages(monkeypatch):
    """记录通过 UniMessage.send 发出的消息"""
    from nonebot_plugin_alconna import UniMessage

    sent: list = []

    async def fake_send(self, target=None, bot=None, **kwargs):
        sent.append((self, target, bot))
        return MagicMock()

    monkeypatch.setattr(UniMessage, "send", fake_send)
    return sent


def _qq_event(text: str = "早上好", group_openid: str = "openid-1"):
    from nonebot.adapters.qq.event import GroupMessageCreateEvent

    event = MagicMock(spec=GroupMessageCreateEvent)
    event.group_openid = group_openid
    event.get_plaintext.return_value = text
    return event


def _qq_bot():
    from nonebot.adapters.qq import Bot as QQBot

    bot = MagicMock(spec=QQBot)
    bot.self_id = "qq-bot"
    return bot


def test_daily_summary_hour_is_six() -> None:
    import nonebot_plugin_message_summary.__main__ as module

    assert module.DAILY_SUMMARY_HOUR == 6


def test_is_group_daily_invocation(monkeypatch) -> None:
    import nonebot_plugin_message_summary.__main__ as module

    monkeypatch.setattr(module, "get_command_prefix", lambda: ".")
    assert module.is_group_daily_invocation(_qq_event(text=".group-daily")) is True
    assert module.is_group_daily_invocation(_qq_event(text="  .group-daily  ")) is True
    # 缺少命令前缀时不会被 alconna 匹配，不应让位
    assert module.is_group_daily_invocation(_qq_event(text="group-daily")) is False
    assert module.is_group_daily_invocation(_qq_event(text=".sign")) is False

    monkeypatch.setattr(module, "get_command_prefix", lambda: "")
    assert module.is_group_daily_invocation(_qq_event(text="group-daily")) is True


@pytest.mark.asyncio
async def test_qq_only_group_pushes_once_after_six(qq_daily_env, stub_summary, sent_messages, monkeypatch) -> None:
    module, enabled, state = qq_daily_env
    enabled.data.append("qq_openid-1")
    monkeypatch.setattr(module, "get_bound_qq_number", AsyncMock(return_value=None))
    bot = _qq_bot()

    await module.try_send_qq_daily_summary(bot, _qq_event(), "qq_openid-1")

    assert stub_summary.await_count == 1
    assert len(sent_messages) == 1
    assert sent_messages[0][1] is not None
    assert state.data["qq_openid-1"] == module.today_key()

    # 同一天的第二条消息不再重复推送
    await module.try_send_qq_daily_summary(bot, _qq_event(text="中午好"), "qq_openid-1")
    assert stub_summary.await_count == 1
    assert len(sent_messages) == 1


@pytest.mark.asyncio
async def test_skips_before_six(qq_daily_env, stub_summary, sent_messages, monkeypatch) -> None:
    module, enabled, _ = qq_daily_env
    enabled.data.append("qq_openid-1")
    monkeypatch.setattr(module, "DAILY_SUMMARY_HOUR", 24)

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(), "qq_openid-1")

    assert stub_summary.await_count == 0
    assert not sent_messages


@pytest.mark.asyncio
async def test_skips_when_summary_disabled(qq_daily_env, stub_summary, sent_messages, monkeypatch) -> None:
    module, _, _ = qq_daily_env
    monkeypatch.setattr(module, "get_bound_qq_number", AsyncMock(return_value=None))

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(), "qq_openid-1")

    assert stub_summary.await_count == 0
    assert not sent_messages


@pytest.mark.asyncio
async def test_skips_when_ob11_still_available(qq_daily_env, stub_summary, sent_messages, monkeypatch) -> None:
    module, enabled, _ = qq_daily_env
    enabled.data.append("qq_openid-1")
    monkeypatch.setattr(module, "get_bound_qq_number", AsyncMock(return_value="10001"))
    monkeypatch.setattr(module, "is_ob11_group_available", AsyncMock(return_value=True))

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(), "qq_openid-1")

    assert stub_summary.await_count == 0
    assert not sent_messages


@pytest.mark.asyncio
async def test_bound_group_uses_qq_number_as_state_key(qq_daily_env, stub_summary, sent_messages, monkeypatch) -> None:
    """已绑定的群即使 OB11 掉线，也不会在当天重复推送"""
    module, enabled, state = qq_daily_env
    enabled.data.append("qq_10001")
    monkeypatch.setattr(module, "get_bound_qq_number", AsyncMock(return_value="10001"))
    monkeypatch.setattr(module, "is_ob11_group_available", AsyncMock(return_value=False))

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(), "qq_openid-1")

    assert len(sent_messages) == 1
    assert state.data["qq_10001"] == module.today_key()
    assert "qq_openid-1" not in state.data


@pytest.mark.asyncio
async def test_skips_when_already_sent(qq_daily_env, stub_summary, sent_messages, monkeypatch) -> None:
    module, enabled, state = qq_daily_env
    enabled.data.append("qq_openid-1")
    state.data["qq_openid-1"] = module.today_key()
    monkeypatch.setattr(module, "get_bound_qq_number", AsyncMock(return_value=None))

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(), "qq_openid-1")

    assert stub_summary.await_count == 0
    assert not sent_messages


@pytest.mark.asyncio
async def test_group_daily_command_is_left_to_the_handler(
    qq_daily_env, stub_summary, sent_messages, monkeypatch
) -> None:
    module, enabled, state = qq_daily_env
    enabled.data.append("qq_openid-1")

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(text=".group-daily"), "qq_openid-1")

    assert stub_summary.await_count == 0
    assert not sent_messages
    assert "qq_openid-1" not in state.data


@pytest.mark.asyncio
async def test_manual_push_before_six_does_not_suppress_auto_push(
    qq_daily_env, stub_summary, sent_messages, monkeypatch
) -> None:
    module, _, state = qq_daily_env
    monkeypatch.setattr(module, "DAILY_SUMMARY_HOUR", 24)

    await module.send_daily_summary_to_qq(_qq_bot(), _qq_event(), "qq_openid-1", "qq_openid-1")

    assert len(sent_messages) == 1
    assert "qq_openid-1" not in state.data


@pytest.mark.asyncio
async def test_ob11_push_uses_v11_bot_and_marks_state(qq_daily_env, stub_summary, monkeypatch) -> None:
    module, _, state = qq_daily_env
    from nonebot.adapters.onebot.v11 import Bot as V11Bot
    from nonebot_plugin_alconna import UniMessage

    # 适配器导出需要真实的 adapter，这里直接替换导出结果
    monkeypatch.setattr(UniMessage, "export", AsyncMock(return_value="exported-message"))
    bot = MagicMock(spec=V11Bot)
    bot.self_id = "ob11"
    bot.send_group_msg = AsyncMock()
    monkeypatch.setattr(module, "get_available_groups", AsyncMock(return_value={"10001": [bot]}))

    await module.send_daily_summary_to_group("qq_10001")

    bot.send_group_msg.assert_awaited_once()
    assert bot.send_group_msg.await_args.kwargs["group_id"] == 10001
    assert bot.send_group_msg.await_args.kwargs["message"] == "exported-message"
    assert state.data["qq_10001"] == module.today_key()


@pytest.mark.asyncio
async def test_ob11_push_ignores_qq_bots(qq_daily_env, stub_summary, monkeypatch) -> None:
    """广播插件支持枚举 QQ 群后，定时任务也不能把 group_openid 当成群号发送"""
    module, _, _ = qq_daily_env
    monkeypatch.setattr(module, "get_available_groups", AsyncMock(return_value={"openid-1": [_qq_bot()]}))

    await module.send_daily_summary_to_group("qq_openid-1")

    assert stub_summary.await_count == 0


@pytest.mark.asyncio
async def test_retries_on_next_message_after_failure(qq_daily_env, sent_messages, monkeypatch) -> None:
    """生成失败时不记录已推送，下一条消息会重试"""
    module, enabled, state = qq_daily_env
    enabled.data.append("qq_openid-1")
    monkeypatch.setattr(module, "get_bound_qq_number", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "md_to_pic", AsyncMock(return_value=b"image-bytes"))
    generate = AsyncMock(side_effect=[RuntimeError("生成失败"), "# 今日总结"])
    monkeypatch.setattr(module, "generate_daily_summary", generate)

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(), "qq_openid-1")
    assert not sent_messages
    assert "qq_openid-1" not in state.data

    await module.try_send_qq_daily_summary(_qq_bot(), _qq_event(text="再来一次"), "qq_openid-1")
    assert len(sent_messages) == 1
    assert state.data["qq_openid-1"] == module.today_key()


@pytest.mark.asyncio
async def test_resolve_state_key(monkeypatch) -> None:
    """群号直接使用，openid 则按绑定关系归一化为群号"""
    import nonebot_plugin_message_summary.__main__ as module

    queried: list[str] = []

    async def fake_bound(openid: str):
        queried.append(openid)
        return "10001" if openid == "openid-bound" else None

    monkeypatch.setattr(module, "get_bound_qq_number", fake_bound)

    assert await module.resolve_state_key("qq_10001") == "qq_10001"
    assert queried == []
    assert await module.resolve_state_key("qq_openid-bound") == "qq_10001"
    assert await module.resolve_state_key("qq_openid-free") == "qq_openid-free"
