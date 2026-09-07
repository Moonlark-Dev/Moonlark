from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 shengcao 插件的 LangHelper.text，避免依赖数据库读取语言文本

    注意：插件导入必须在函数/fixture 内部进行（collection 阶段 nonebot 插件尚未加载）。
    """
    from nonebot_plugin_shengcao.main import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


@pytest.mark.asyncio
async def test_build_qq_message_grass_has_retry_and_fury_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人 /grass 回复应附加 @ 并以 markdown 渲染，键盘含 再试一次/狂怒模式 两个按钮"""
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage
    from nonebot_plugin_shengcao.main import _build_qq_message
    from nonebot_plugin_larkutils.command import config

    monkeypatch.setattr(config, "command_start", ["/"])

    message = await _build_qq_message("10", "草*草", "原始文本", "grass")

    assert isinstance(message, UniMessage)
    # 文本保持原有内容（含转义），且最前面附加 @ (qqbot-at-user)
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == '<qqbot-at-user id="10" />草\\*草'
    assert any("markdown" in styles for styles in text.styles.values())
    # 键盘包含 再试一次/狂怒模式 两个 enter 按钮
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    buttons = list(keyboard.children)
    assert [button.text for button in buttons] == ["/grass 原始文本", "/grass-fury 原始文本"]
    assert [str(button.label) for button in buttons] == ["text::button.retry", "text::button.fury"]


@pytest.mark.asyncio
async def test_build_qq_message_furry_uses_uwu_and_owo_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """福瑞彩蛋模式下键盘按钮文案应为 UwU / OwO，且再试一次回到 grass-furry"""
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage
    from nonebot_plugin_shengcao.main import _build_qq_message
    from nonebot_plugin_larkutils.command import config

    monkeypatch.setattr(config, "command_start", ["/"])

    message = await _build_qq_message("10", "本兽 嗷呜~🐾", "我啊", "furry")

    assert isinstance(message, UniMessage)
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == '<qqbot-at-user id="10" />本兽 嗷呜~🐾'
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    buttons = list(keyboard.children)
    assert [button.text for button in buttons] == ["/grass-furry 我啊", "/grass-fury 我啊"]
    assert [str(button.label) for button in buttons] == ["UwU", "OwO"]


@pytest.mark.asyncio
async def test_fury_text_replaces_all_matched_words_deterministically() -> None:
    """狂怒模式：命中词典的词必须全部被替换，且结果确定（无随机）"""
    from nonebot_plugin_shengcao.main import fury_text

    first = fury_text("一 一 一")
    second = fury_text("一 一 一")
    assert first == second
    assert "一" not in first


def test_escape_markdown_escapes_special_characters() -> None:
    """集中到 larkutils 的 escape_markdown 应转义 markdown 特殊字符"""
    from nonebot_plugin_larkutils import escape_markdown

    assert escape_markdown("草*草 _x_ [a](b) <tag> #h |p| `c`!") == (
        "草\\*草 \\_x\\_ \\[a\\]\\(b\\) \\<tag\\> \\#h \\|p\\| \\`c\\`\\!"
    )
    assert escape_markdown("普通文本，没有特殊字符 🐾") == "普通文本，没有特殊字符 🐾"


@pytest.mark.asyncio
async def test_shengcao_text_furry_applies_extra_dictionary() -> None:
    """福瑞模式应用额外词典："我" -> "本兽"，语气词 -> "嗷呜~" """
    from nonebot_plugin_shengcao.main import shengcao_text

    result = shengcao_text("我 啊 你好", furrified=True)
    assert "本兽" in result
    assert "嗷呜~" in result


@pytest.mark.asyncio
async def test_furry_reply_appends_paw_emoji(monkeypatch: pytest.MonkeyPatch) -> None:
    """福瑞模式的回答应附带 🐾 emoji（由 handler 追加）"""
    from unittest.mock import MagicMock

    from nonebot_plugin_shengcao.main import _process_grass, grass_furry_cmd, lang

    monkeypatch.setattr("nonebot_plugin_shengcao.main.review_text", AsyncMock(return_value={"compliance": True}))
    finish = AsyncMock()
    monkeypatch.setattr(lang, "finish", finish)

    await _process_grass(grass_furry_cmd, MagicMock(), MagicMock(), "10", "我 啊", "furry")

    args = finish.call_args.args
    assert args[0] == "result"
    assert "本兽" in args[2]
    assert "嗷呜~" in args[2]
    assert args[2].endswith("🐾")
