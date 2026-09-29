"""nonebot-plugin-jev 测试：问题本地化、请求体构造、答案解析与 ask() 行为"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

if TYPE_CHECKING:
    from nonebot_plugin_jev.types import Question


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._data


class _FakeClient:
    """记录 post 调用并返回预置数据"""

    def __init__(self, data: Any, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.data)


def _patch_lang(monkeypatch: pytest.MonkeyPatch, text: AsyncMock) -> None:
    from nonebot_plugin_jev.utils import query as query_module

    monkeypatch.setattr(query_module.lang, "text", text)


async def test_build_payload_resolves_lang_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    """LangRef 应在请求前解析为本地化文本，普通字符串原样保留"""
    from nonebot_plugin_jev import choice, lang_ref, noul, score
    from nonebot_plugin_jev.utils.query import build_payload

    async def fake_text(key: str, lang_str: str, *args: Any, **kwargs: Any) -> str:
        return f"{lang_str}|{key}|{','.join(str(a) for a in args)}"

    _patch_lang(monkeypatch, AsyncMock(side_effect=fake_text))

    questions: dict[str, Question] = {
        "flag": noul(lang_ref("pre_trigger.truncate")),
        "tag": noul("直接给定的文本"),
        "mood": choice(
            lang_ref("reply.mood.instructions", "附加参数"),
            criteria={"joy": lang_ref("reply.mood.criteria.joy"), "none": "无变化"},
        ),
        "level": score("打分", criteria=[lang_ref("levels.0"), lang_ref("levels.1")]),
    }

    payload = await build_payload("state 文本", questions, "en_us", model="jev-test")

    assert payload["state"] == "state 文本"
    assert payload["model"] == "jev-test"
    assert payload["questions"]["flag"] == {
        "type": "noul",
        "instructions": "en_us|pre_trigger.truncate|",
    }
    assert payload["questions"]["tag"]["instructions"] == "直接给定的文本"
    assert payload["questions"]["mood"] == {
        "type": "choice",
        "instructions": "en_us|reply.mood.instructions|附加参数",
        "criteria": {"joy": "en_us|reply.mood.criteria.joy|", "none": "无变化"},
    }
    assert payload["questions"]["level"]["criteria"] == ["en_us|levels.0|", "en_us|levels.1|"]


async def test_build_payload_structured_instructions(monkeypatch: pytest.MonkeyPatch) -> None:
    """instructions 允许是结构化对象（问题 + 引用的数据字段）"""
    from nonebot_plugin_jev import choice, lang_ref
    from nonebot_plugin_jev.utils.query import build_payload

    async def fake_text(key: str, lang_str: str, *args: Any, **kwargs: Any) -> str:
        return key

    _patch_lang(monkeypatch, AsyncMock(side_effect=fake_text))

    payload = await build_payload(
        {},
        {
            "note_1": choice(
                {"question": lang_ref("note_review.question"), "note": "[#1] 内容"}, criteria={"keep": "保留"}
            )
        },
        "zh_hans",
    )

    question = payload["questions"]["note_1"]
    assert question["instructions"] == {"question": "note_review.question", "note": "[#1] 内容"}
    assert question["criteria"] == {"keep": "保留"}


def test_parse_answer_accepts_valid_and_rejects_invalid() -> None:
    from nonebot_plugin_jev import choice, noul, score
    from nonebot_plugin_jev.types import ChoiceAnswer, NoulAnswer, ScoreAnswer
    from nonebot_plugin_jev.utils.query import _parse_answer

    assert isinstance(_parse_answer(noul("x"), {"noul": 0.7}), NoulAnswer)
    parsed = _parse_answer(
        choice("x", criteria={"a": "A"}), {"choice": "a", "confidence": 0.9, "probabilities": {"a": 0.9}}
    )
    assert isinstance(parsed, ChoiceAnswer)
    assert parsed.choice == "a" and parsed.confidence == 0.9
    assert isinstance(_parse_answer(score("x", criteria=["低", "高"]), {"score": 1.4}), ScoreAnswer)

    # 缺字段 / 类型不对的答案应被拒绝（返回 None 而不是抛异常）
    assert _parse_answer(noul("x"), {"noul": "不是数字"}) is None
    assert _parse_answer(noul("x"), {}) is None
    assert _parse_answer(noul("x"), None) is None
    assert _parse_answer(choice("x", criteria={}), {"choice": 1}) is None


async def test_ask_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_jev import noul
    from nonebot_plugin_jev.config import config
    from nonebot_plugin_jev.utils.query import JevNotConfigured, ask

    monkeypatch.setattr(config, "typesafe_api_key", "")
    with pytest.raises(JevNotConfigured):
        await ask("state", {"q": noul("问题")})


async def test_ask_returns_typed_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_jev import noul
    from nonebot_plugin_jev.config import config
    from nonebot_plugin_jev.types import NoulAnswer
    from nonebot_plugin_jev.utils import query as query_module
    from nonebot_plugin_jev.utils.query import ask

    monkeypatch.setattr(config, "typesafe_api_key", "test-key")
    fake = _FakeClient({"answers": {"urgent": {"noul": 0.8}, "broken": {"noul": "bad"}}})
    monkeypatch.setattr(query_module, "client", fake)

    answers = await ask(
        "state", {"urgent": noul("是否紧急"), "broken": noul("坏答案")}, identify="Test", lang_str="zh_hans"
    )

    url, kwargs = fake.calls[0]
    assert url == "/systemone"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == config.typesafe_model
    assert isinstance(answers["urgent"], NoulAnswer)
    assert answers["urgent"].noul == 0.8
    # 无效答案被跳过而不是抛异常
    assert "broken" not in answers


async def test_ask_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_jev import noul
    from nonebot_plugin_jev.config import config
    from nonebot_plugin_jev.utils import query as query_module
    from nonebot_plugin_jev.utils.query import JevError, ask

    monkeypatch.setattr(config, "typesafe_api_key", "test-key")
    monkeypatch.setattr(config, "typesafe_max_retries", 1)
    fake = _FakeClient(None, error=httpx.ConnectError("boom"))
    monkeypatch.setattr(query_module, "client", fake)
    # 跳过重试之间的 sleep
    monkeypatch.setattr(query_module.asyncio, "sleep", AsyncMock())

    with pytest.raises(JevError):
        await ask("state", {"q": noul("问题")})
    # 首次 + 1 次重试
    assert len(fake.calls) == 2
