"""nonebot_plugin_vote 的 QQ 官方渲染回归测试。

QQ 官方机器人下：
- 投票列表改为 markdown，标题使用 <qqbot-cmd-input> 变成可点击指令；
- 投票详情改为 markdown，选项通过键盘按钮选择。
"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

_VOTE_LANG = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "vote.yaml"


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


@pytest.fixture
def vote_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """按真实 vote.yaml 渲染文案，并把命令前缀固定为 `/`"""
    import nonebot_plugin_vote.utils as module
    from nonebot_plugin_larklang.__main__ import LangHelper, remove_trailing_blank_lines

    templates = _flatten(yaml.safe_load(_VOTE_LANG.read_text(encoding="utf-8")))

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *args: object) -> str:
        return remove_trailing_blank_lines(templates[key].format(*args, __prefix__="/"))

    monkeypatch.setattr(LangHelper, "text", fake_text)
    monkeypatch.setattr(module, "get_command_prefix", lambda: "/")
    return module


def _fake_vote(title: str = "今晚吃什么", open_: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=3,
        title=title,
        content="来投票吧",
        sponsor="10",
        group=None,
        end_time=datetime.now() + timedelta(hours=2) if open_ else datetime.now() - timedelta(hours=2),
    )


def _vote_list_of(vote: SimpleNamespace):
    async def fake_vote_list(_show_all: bool, _group_id: str, _session: object):
        yield vote, vote.end_time > datetime.now()

    return fake_vote_list


def _empty_vote_list():
    async def fake_vote_list(_show_all: bool, _group_id: str, _session: object):
        if False:  # pragma: no cover - 空的异步生成器
            yield None, None

    return fake_vote_list


@pytest.mark.asyncio
async def test_vote_list_markdown_uses_clickable_title(vote_env, monkeypatch: pytest.MonkeyPatch) -> None:
    module = vote_env
    monkeypatch.setattr(module, "get_vote_list", _vote_list_of(_fake_vote()))

    markdown = await module.build_vote_list_markdown("10", "qq_10000", MagicMock(), False)

    assert markdown.startswith("## 投票列表")
    assert '- <qqbot-cmd-input text="/vote 3" show="今晚吃什么" reference="false" />（进行中）' in markdown


@pytest.mark.asyncio
async def test_vote_list_markdown_escapes_special_characters(vote_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """标题里的 < > " 等字符必须编码，避免破坏 <qqbot-cmd-input> 标签"""
    module = vote_env
    monkeypatch.setattr(module, "get_vote_list", _vote_list_of(_fake_vote(title='<b>"标题"</b>')))

    markdown = await module.build_vote_list_markdown("10", "qq_10000", MagicMock(), False)

    assert "<b>" not in markdown
    assert "%3C" in markdown and "%22" in markdown


@pytest.mark.asyncio
async def test_vote_list_markdown_empty(vote_env, monkeypatch: pytest.MonkeyPatch) -> None:
    module = vote_env
    monkeypatch.setattr(module, "get_vote_list", _empty_vote_list())

    markdown = await module.build_vote_list_markdown("10", "qq_10000", MagicMock(), False)
    assert markdown == "## 投票列表\n> 当前没有进行中的投票。"


@pytest.mark.asyncio
async def test_vote_detail_markdown_and_buttons(vote_env, monkeypatch: pytest.MonkeyPatch) -> None:
    module = vote_env
    vote = _fake_vote()

    monkeypatch.setattr(module, "is_user_voted", AsyncMock(return_value=False))
    monkeypatch.setattr(
        module,
        "get_choice",
        AsyncMock(
            return_value=[
                {"id": 1, "text": "火锅", "count": 3, "percent": 30},
                {"id": 2, "text": "烧烤", "count": 7, "percent": 70},
            ],
        ),
    )
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=SimpleNamespace(nickname="发起人")))

    class _FakeScalars:
        def all(self) -> list:
            return []

    session = MagicMock()
    session.scalars = AsyncMock(return_value=_FakeScalars())

    markdown = await module.build_vote_markdown("10", session, vote)
    assert markdown.startswith("## 今晚吃什么")
    assert "1. 火锅 — 3 票（30%）" in markdown
    assert "2. 烧烤 — 7 票（70%）" in markdown

    buttons = await module.build_vote_buttons("10", session, vote)
    assert [str(button.label) for button in buttons] == ["1. 火锅", "2. 烧烤"]
    assert [button.text for button in buttons] == ["/vote 3 1", "/vote 3 2"]


@pytest.mark.asyncio
async def test_vote_buttons_hidden_when_closed_or_voted(vote_env, monkeypatch: pytest.MonkeyPatch) -> None:
    module = vote_env

    class _FakeScalars:
        def all(self) -> list:
            return []

    session = MagicMock()
    session.scalars = AsyncMock(return_value=_FakeScalars())

    monkeypatch.setattr(module, "is_user_voted", AsyncMock(return_value=False))
    assert await module.build_vote_buttons("10", session, _fake_vote(open_=False)) == []

    monkeypatch.setattr(module, "is_user_voted", AsyncMock(return_value=True))
    assert await module.build_vote_buttons("10", session, _fake_vote()) == []


def test_truncate_button_label() -> None:
    from nonebot_plugin_vote.utils import build_choice_button_label, truncate_button_label

    assert truncate_button_label("火锅") == "火锅"
    # 超过 10 个字符时截断并追加省略号
    assert truncate_button_label("一二三四五六七八九十一二") == "一二三四五六七八九…"
    assert truncate_button_label("换\n行") == "换 行"

    # 选项按钮的整体长度（含编号）也不超过限制
    assert build_choice_button_label(1, "火锅") == "1. 火锅"
    assert len(build_choice_button_label(2, "一二三四五六七八九十一二")) == 10
    assert build_choice_button_label(2, "一二三四五六七八九十一二").startswith("2. ")
