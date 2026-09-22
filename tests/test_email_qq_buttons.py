"""nonebot_plugin_email 的 QQ 官方按钮回归测试。

QQ 官方机器人下，未读邮件列表发送后会附带「一键领取」「全部已读」按钮；
其余平台仍只发送邮件列表图片。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class _Finished(Exception):
    """用于截断 matcher.finish 的哨兵异常"""


class _FakeLang:
    def __init__(self, templates: dict[str, str]) -> None:
        self.templates = templates

    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return self.templates.get(key, key).format(*args)

    async def finish(self, key: str, _user_id: str, *args: object) -> None:
        raise _Finished(key)

    async def send(self, key: str, _user_id: str, *args: object) -> None:
        return None


_TEMPLATES = {
    "email_list.title": "邮件列表",
    "email_list.claimed": "已领取",
    "email_list.time": "时间: {}",
    "email_list.from": "来自: {}",
    "email_list.email_id": "邮件 ID: {}",
    "button.claim_all": "一键领取",
    "button.read_all": "全部已读",
}


@pytest.fixture
def email_env(monkeypatch: pytest.MonkeyPatch):
    import nonebot_plugin_email.commands.email as module

    async def empty_unread(_user_id: str):
        if False:  # pragma: no cover - 空的异步生成器
            yield None

    monkeypatch.setattr(module, "render_template", AsyncMock(return_value=b"image-bytes"))
    monkeypatch.setattr(module, "get_unread_email", empty_unread)
    monkeypatch.setattr(module, "mark_email_read", AsyncMock(return_value=1))
    monkeypatch.setattr(module, "lang", _FakeLang(_TEMPLATES))
    monkeypatch.setattr(module, "get_command_prefix", lambda: "/")
    return module


def _get_buttons(message) -> list:
    from nonebot_plugin_alconna.uniseg import Keyboard

    return next(seg for seg in message if isinstance(seg, Keyboard)).children


@pytest.mark.asyncio
async def test_qq_email_list_has_claim_and_read_buttons(email_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot.adapters.qq import Bot as QQBot

    module = email_env
    sent: list = []

    async def fake_send(self, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    finish = AsyncMock()
    monkeypatch.setattr(module.UniMessage, "send", fake_send)
    monkeypatch.setattr(module.email, "finish", finish)

    await module._(bot=MagicMock(spec=QQBot), user_id="10")

    assert len(sent) == 1
    buttons = _get_buttons(sent[0])
    assert [str(button.label) for button in buttons] == ["一键领取", "全部已读"]
    assert [button.text for button in buttons] == ["/email claim all", "/email read all"]
    finish.assert_awaited()


@pytest.mark.asyncio
async def test_other_adapter_email_list_stays_image_only(email_env, monkeypatch: pytest.MonkeyPatch) -> None:
    module = email_env
    send = AsyncMock()
    finish = AsyncMock()
    monkeypatch.setattr(module.UniMessage, "send", send)
    monkeypatch.setattr(module.email, "finish", finish)

    await module._(bot=MagicMock(), user_id="10")

    send.assert_not_awaited()
    finish.assert_awaited_once()
