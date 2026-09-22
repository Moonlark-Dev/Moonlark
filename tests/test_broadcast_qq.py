"""nonebot_plugin_broadcast 的 QQ 适配器优化回归测试。

覆盖：
1. QQ 官方机器人直接以 markdown 发送广播（渲染图片的行为只保留给其余平台）；
2. 自定义按钮只出现在 QQ 官方的广播消息里；
3. 可通过 GroupBind 枚举 QQ 官方群聊，且与 OB11 群去重；
4. `bcsu button clear` 不会被顶层 `clear` 子命令抢占。
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


class _Finished(Exception):
    """用于截断 lang.finish 的哨兵异常"""


class _RecordingLang:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return f"{key}"

    async def finish(self, key: str, _user_id: str, *args: object) -> None:
        self.calls.append((key, args))
        raise _Finished(key)

    async def send(self, key: str, _user_id: str, *args: object) -> None:
        self.calls.append((key, args))


@pytest.fixture
def broadcast_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """把广播数据文件指向临时目录，避免污染真实 localstore"""
    import nonebot_plugin_broadcast.__main__ as module

    data_file = tmp_path / "data.json"
    monkeypatch.setattr(module, "data_file", data_file)
    lang = _RecordingLang()
    monkeypatch.setattr(module, "lang", lang)
    return module, data_file, lang


def _get_markdown(message) -> str:
    from nonebot_plugin_alconna.uniseg import Text

    return next(seg for seg in message if isinstance(seg, Text)).text


def _is_markdown(message) -> bool:
    from nonebot_plugin_alconna.uniseg import Text

    text = next(seg for seg in message if isinstance(seg, Text))
    return any("markdown" in styles for styles in text.styles.values())


def _get_buttons(message) -> list:
    from nonebot_plugin_alconna.uniseg import Keyboard

    return next(seg for seg in message if isinstance(seg, Keyboard)).children


def test_bcsu_button_clear_not_hijacked_by_top_level_clear() -> None:
    """`bcsu button clear` 必须命中 button 子命令，而不是顶层的 clear

    这里用工厂函数重新构造一份未被事件响应器改写（未附加命令前缀）的副本，
    解析行为与运行时一致。
    """
    from nonebot_plugin_broadcast.__main__ import build_bcsu_alconna

    alc = build_bcsu_alconna()

    result = alc.parse("bcsu button clear")
    assert result.matched
    assert "button" in result.subcommands
    assert "clear" not in result.subcommands
    assert result.all_matched_args["action"] == "clear"

    result = alc.parse("bcsu clear")
    assert result.matched
    assert "clear" in result.subcommands
    assert "button" not in result.subcommands

    result = alc.parse("bcsu button add 签到 /sign")
    assert result.matched
    assert result.all_matched_args["action"] == "add"
    assert result.all_matched_args["label"] == "签到"
    assert tuple(result.all_matched_args["text"]) == ("/sign",)

    result = alc.parse("bcsu button add 攻略 /help 商店")
    assert result.matched
    assert tuple(result.all_matched_args["text"]) == ("/help", "商店")

    result = alc.parse("bcsu 这是一条广播")
    assert result.matched
    assert "button" not in result.subcommands
    assert tuple(result.all_matched_args["content"]) == ("这是一条广播",)


def test_qq_broadcast_message_uses_markdown_and_buttons() -> None:
    import nonebot_plugin_broadcast.__main__ as module

    message = module.build_qq_broadcast_message("## 停机维护", [{"label": "签到", "text": "/sign"}])
    assert _is_markdown(message)
    assert _get_markdown(message) == "## 停机维护"
    buttons = _get_buttons(message)
    assert [str(button.label) for button in buttons] == ["签到"]
    assert buttons[0].text == "/sign"


def test_qq_broadcast_message_without_buttons() -> None:
    import nonebot_plugin_broadcast.__main__ as module

    message = module.build_qq_broadcast_message("广播内容", [])
    assert _is_markdown(message)
    assert not any(seg.__class__.__name__ == "Keyboard" for seg in message)


@pytest.mark.asyncio
async def test_qq_broadcast_skips_image_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方下长广播也直接发 markdown，不再渲染图片"""
    import nonebot_plugin_broadcast.__main__ as module
    from nonebot.adapters.qq import Bot as QQBot

    md_to_pic = AsyncMock()
    monkeypatch.setattr(module, "md_to_pic", md_to_pic)

    content = "长广播内容" * 100
    message = await module.build_broadcast_message(MagicMock(spec=QQBot), content, [])

    md_to_pic.assert_not_awaited()
    assert _is_markdown(message)
    assert _get_markdown(message) == content


@pytest.mark.asyncio
async def test_other_adapter_keeps_image_behavior(monkeypatch: pytest.MonkeyPatch, broadcast_env) -> None:
    """其余平台保持原行为：长内容渲染为图片，短内容发送纯文本"""
    module, _, _ = broadcast_env
    from nonebot_plugin_alconna.uniseg import Image, Text

    md_to_pic = AsyncMock(return_value=b"image-bytes")
    monkeypatch.setattr(module, "md_to_pic", md_to_pic)

    long_message = await module.build_broadcast_message(MagicMock(), "长内容" * 100, [])
    md_to_pic.assert_awaited_once()
    assert any(isinstance(seg, Image) for seg in long_message)

    short_message = await module.build_broadcast_message(MagicMock(), "短内容", [])
    assert any(isinstance(seg, Text) for seg in short_message)


@pytest.mark.asyncio
async def test_get_available_groups_includes_qq_and_dedupes(broadcast_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方群通过 GroupBind 枚举；已被 OB11 覆盖的群不重复推送"""
    module, data_file, _ = broadcast_env
    from nonebot.adapters.onebot.v11 import Bot as V11Bot
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_bots.models import GroupBind
    from nonebot_plugin_orm import get_session

    async with get_session() as session:
        session.add(GroupBind(group_qq_number="10001", group_openid="openid-bound"))
        session.add(GroupBind(group_qq_number="20002", group_openid="openid-unbound"))
        await session.commit()

    v11_bot = MagicMock(spec=V11Bot)
    v11_bot.self_id = "v11"
    v11_bot.get_group_list = AsyncMock(return_value=[{"group_id": 10001}])
    qq_bot = MagicMock(spec=QQBot)
    qq_bot.self_id = "qq"

    monkeypatch.setattr(module, "get_bots", lambda: {"v11": v11_bot, "qq": qq_bot})

    groups = await module.get_available_groups()
    # 已绑定且 OB11 在线覆盖的群不再通过 QQ 推送，未绑定的群使用 openid
    assert "10001" in groups
    assert "openid-unbound" in groups
    assert "openid-bound" not in groups
    assert groups["openid-unbound"] == [qq_bot]

    # 群开关对同一物理群生效：禁用群号后 QQ 侧也不再推送
    data_file.write_text(
        json.dumps(
            {
                "counter": {"update_at": [2026, 1], "sent_count": 0},
                "latest": "",
                "disabled_groups": ["20002"],
                "buttons": [],
            },
        ),
        encoding="utf-8",
    )
    groups = await module.get_available_groups()
    assert "openid-unbound" not in groups
    assert "10001" in groups


@pytest.mark.asyncio
async def test_handle_button_add_and_remove(broadcast_env) -> None:
    import nonebot_plugin_broadcast.__main__ as module

    _, data_file, lang = broadcast_env

    with pytest.raises(_Finished):
        await module.handle_button(
            action=MagicMock(available=True, result="add"),
            label=MagicMock(available=True, result="签到"),
            text=MagicMock(available=True, result=["/sign"]),
            user_id="u",
        )
    assert lang.calls[-1][0] == "bcsu.button_added"

    data = json.loads(data_file.read_text(encoding="utf-8"))
    assert data["buttons"] == [{"label": "签到", "text": "/sign"}]

    with pytest.raises(_Finished):
        await module.handle_button(
            action=MagicMock(available=True, result="remove"),
            label=MagicMock(available=True, result="签到"),
            text=MagicMock(available=False, result=None),
            user_id="u",
        )
    assert lang.calls[-1][0] == "bcsu.button_removed"
    assert json.loads(data_file.read_text(encoding="utf-8"))["buttons"] == []


@pytest.mark.asyncio
async def test_handle_button_requires_command(broadcast_env) -> None:
    """add 缺少指令时给出用法提示，不写入按钮"""
    import nonebot_plugin_broadcast.__main__ as module

    _, data_file, lang = broadcast_env

    with pytest.raises(_Finished):
        await module.handle_button(
            action=MagicMock(available=True, result="add"),
            label=MagicMock(available=True, result="签到"),
            text=MagicMock(available=True, result=[]),
            user_id="u",
        )
    assert lang.calls[-1][0] == "bcsu.button_usage"
    assert not data_file.exists()
