"""nonebot_plugin_larkcave 在 QQ 官方适配器下改用 Markdown 展示的回归测试。

普通消息里的图片会被 QQ 排到消息最前面，因此 QQ 官方机器人下的回声洞改为 Markdown
发送，图片保持在投稿正文中的原位置；其余适配器仍发送原来的分段消息。
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _qq_bot() -> Any:
    from nonebot.adapters.qq import Bot as QQBot

    bot = MagicMock(spec=QQBot)
    bot.self_id = "102000001"
    return bot


@pytest.mark.asyncio
async def test_parse_content_markdown_inlines_images_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """正文中的图片要转成 Markdown 图片语法，并保留在原来的文字位置。"""
    from nonebot_plugin_larkcave.utils import decoder

    async def fake_get_image(match: str, _session: Any) -> Any:
        assert match == "[[Img:1674571532.0250726]]]"
        return SimpleNamespace(data=b"png")

    async def fake_image_markdown(data: bytes, _bot: Any) -> str:
        assert data == b"png"
        return "![text #120px #80px](qqbot-media://image/v1/token)"

    monkeypatch.setattr(decoder, "get_image_by_match", fake_get_image)
    monkeypatch.setattr(decoder, "create_image_markdown", fake_image_markdown)

    markdown = await decoder.parse_content_markdown("前面\n[[Img:1674571532.0250726]]]\n后面", None, _qq_bot())

    assert markdown == "前面\n![text #120px #80px](qqbot-media://image/v1/token)\n后面"


@pytest.mark.asyncio
async def test_parse_content_markdown_escapes_text_and_entities() -> None:
    """投稿正文的转义方括号要还原，Markdown 特殊字符要转义，避免破坏排版。"""
    from nonebot_plugin_larkcave.utils import decoder

    markdown = await decoder.parse_content_markdown("&#91;不是图片&#93; *加粗* <x>", None, _qq_bot())

    assert markdown == r"\[不是图片\] \*加粗\* \<x\>"


@pytest.mark.asyncio
async def test_decode_cave_markdown_keeps_image_between_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """解码后的 Markdown 应包含标题、原位图片与页脚。"""
    from nonebot_plugin_larkcave.utils import decoder

    cave = SimpleNamespace(id=42, content="前文[[Img:1674571532.0250726]]]后文", author="author")

    async def fake_text(key: str, _user_id: str, *args: object) -> str:
        return {"render.header": "回声洞 —— ({})", "render.footer": "\n——{}"}[key].format(*args)

    async def fake_get_image(_match: str, _session: Any) -> Any:
        return SimpleNamespace(data=b"png", name="a.png")

    async def fake_image_markdown(_data: bytes, _bot: Any) -> str:
        return "![text #1px #1px](qqbot-media://token)"

    monkeypatch.setattr(decoder, "lang", SimpleNamespace(text=fake_text))
    monkeypatch.setattr(decoder, "get_image_by_match", fake_get_image)
    monkeypatch.setattr(decoder, "create_image_markdown", fake_image_markdown)
    monkeypatch.setattr(decoder, "get_user", AsyncMock(return_value=SimpleNamespace(get_nickname=lambda: "作者")))

    markdown = await decoder.decode_cave_markdown(cave, None, "u", _qq_bot())

    assert markdown == "回声洞 —— \\(42\\)\n前文![text #1px #1px](qqbot-media://token)后文\n——作者"


@pytest.mark.asyncio
async def test_decode_cave_markdown_special_mode_keeps_image_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    """倒序模式下只反转文字，图片的 Markdown 语法必须保持完整。"""
    from nonebot_plugin_larkcave.utils import decoder

    cave = SimpleNamespace(id=42, content="前文[[Img:1674571532.0250726]]]后文", author="author")

    async def fake_text(key: str, _user_id: str, *args: object) -> str:
        return {"render.header": "回声洞 —— ({})", "render.footer": "\n——{}"}[key].format(*args)

    async def fake_get_image(_match: str, _session: Any) -> Any:
        return SimpleNamespace(data=b"png", name="a.png")

    async def fake_image_markdown(_data: bytes, _bot: Any) -> str:
        return "![text #1px #1px](qqbot-media://token)"

    monkeypatch.setattr(decoder, "lang", SimpleNamespace(text=fake_text))
    monkeypatch.setattr(decoder, "get_image_by_match", fake_get_image)
    monkeypatch.setattr(decoder, "create_image_markdown", fake_image_markdown)
    monkeypatch.setattr(decoder, "get_user", AsyncMock(return_value=SimpleNamespace(get_nickname=lambda: "作者")))

    markdown = await decoder.decode_cave_markdown(cave, None, "u", _qq_bot(), use_special=True)

    assert "![text #1px #1px](qqbot-media://token)" in markdown
    assert "\\)24\\( —— 洞声回" in markdown
    assert "文前" in markdown
    assert "文后" in markdown


@pytest.mark.asyncio
async def test_build_cave_message_uses_markdown_for_qq_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人下构造带 markdown 样式的消息，并带上前后缀文案。"""
    from nonebot_plugin_larkcave.utils import decoder

    async def fake_decode_cave_markdown(*_args: Any, **_kwargs: Any) -> str:
        return "正文"

    monkeypatch.setattr(decoder, "decode_cave_markdown", fake_decode_cave_markdown)

    message = await decoder.build_cave_message(
        SimpleNamespace(),
        None,
        "u",
        _qq_bot(),
        prefix="相似：\n",
        suffix="\n相似度 90%",
    )

    assert len(message) == 1
    assert message[0].text == "相似：\n正文\n相似度 90%"
    assert message[0].extract_most_style() == "markdown"


@pytest.mark.asyncio
async def test_build_cave_message_keeps_plain_for_other_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 官方适配器仍使用原来的分段消息。"""
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_larkcave.utils import decoder

    async def fake_decode_cave(*_args: Any, **_kwargs: Any) -> Any:
        return UniMessage(Text("普通消息"))

    monkeypatch.setattr(decoder, "decode_cave", fake_decode_cave)

    message = await decoder.build_cave_message(SimpleNamespace(), None, "u", MagicMock())

    assert message.extract_plain_text() == "普通消息"
    assert message[0].extract_most_style() == ""


@pytest.mark.asyncio
async def test_build_cave_message_falls_back_when_markdown_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """图片上传等原因导致 Markdown 渲染失败时回退为普通消息。"""
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_larkcave.utils import decoder

    async def failing_markdown(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("素材上传失败")

    async def fake_decode_cave(*_args: Any, **_kwargs: Any) -> Any:
        return UniMessage(Text("普通消息"))

    monkeypatch.setattr(decoder, "decode_cave_markdown", failing_markdown)
    monkeypatch.setattr(decoder, "decode_cave", fake_decode_cave)

    message = await decoder.build_cave_message(SimpleNamespace(), None, "u", _qq_bot())

    assert message.extract_plain_text() == "普通消息"
    assert message[0].extract_most_style() == ""


@pytest.mark.asyncio
async def test_send_cave_passes_bot_to_markdown_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    """随机回声洞的发送路径要把当前 bot 传进去，QQ 官方才会走 Markdown 分支。"""
    from nonebot_plugin_larkcave.utils import cave as module

    bot = _qq_bot()
    cave_data = SimpleNamespace(id=398)
    calls: dict[str, Any] = {}

    class _FakeMessage:
        async def send(self) -> Any:
            return SimpleNamespace(msg_ids=[{"message_id": "1"}])

    async def fake_get_cave(_session: Any) -> Any:
        return cave_data

    async def fake_build(cave: Any, _session: Any, _user_id: str, bot_arg: Any, use_special: bool = False) -> Any:
        calls.update(cave=cave, bot=bot_arg, use_special=use_special)
        return _FakeMessage()

    async def fake_get_comments(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(module, "get_cave", fake_get_cave)
    monkeypatch.setattr(module, "build_cave_message", fake_build)
    monkeypatch.setattr(module, "get_comments", fake_get_comments)
    monkeypatch.setattr(module, "on_use", AsyncMock())
    monkeypatch.setattr(module, "add_cave_message", MagicMock())

    await module.send_cave(None, "u", "g", bot)

    assert calls["cave"] is cave_data
    assert calls["bot"] is bot
    assert calls["use_special"] is True
