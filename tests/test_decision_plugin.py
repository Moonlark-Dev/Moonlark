"""nonebot-plugin-decision 测试：问题本地化、state 规范化、请求体构造、答案解析与 ask() 行为"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import httpx
import pytest

if TYPE_CHECKING:
    from nonebot_plugin_decision.types import Question


class _FakeResponse:
    def __init__(self, data: Any, status_code: int = 200, text: str = "") -> None:
        self._data = data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions")
            response = httpx.Response(self.status_code, text=self.text, request=request)
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=request, response=response)

    def json(self) -> Any:
        return self._data


class _FakeClient:
    """记录 post 调用并返回预置数据或抛异常"""

    def __init__(
        self,
        data: Any = None,
        *,
        error: Exception | None = None,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self.data = data
        self.error = error
        self.status_code = status_code
        self.text = text
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.data, status_code=self.status_code, text=self.text)


def _patch_lang(monkeypatch: pytest.MonkeyPatch, text: AsyncMock) -> None:
    from nonebot_plugin_decision.utils import query as query_module

    monkeypatch.setattr(query_module.lang, "text", text)


async def test_build_payload_resolves_lang_refs_and_question_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """LangRef 应在请求前解析为本地化文本，支持 noul / choice / score / box"""
    from nonebot_plugin_decision import box, choice, lang_ref, noul, score
    from nonebot_plugin_decision.utils.query import build_payload

    async def fake_text(key: str, lang_str: str, *args: Any) -> str:
        return f"{lang_str}|{key}|{','.join(str(a) for a in args)}"

    _patch_lang(monkeypatch, AsyncMock(side_effect=fake_text))

    questions: dict[str, Question] = {
        "flag": noul(lang_ref("pre_trigger.truncate")),
        "with_criteria": noul("是否紧急", true=lang_ref("urgent.true"), false="普通事项"),
        "mood": choice(
            lang_ref("reply.mood.instructions", "附加参数"),
            criteria={"joy": lang_ref("reply.mood.criteria.joy"), "none": "无变化", "visual_only": None},
        ),
        "level": score("打分", criteria=[lang_ref("levels.0"), lang_ref("levels.1")]),
        "target_box": box(lang_ref("vision.find_cat")),
    }

    payload = await build_payload(
        "state 文本",
        questions,
        "en_us",
        model="google/gemini-decision-1",
        session_id="s" * 300,
        provider={"allow_fallbacks": True},
    )

    assert payload["state"] == "state 文本"
    assert payload["model"] == "google/gemini-decision-1"
    assert len(payload["session_id"]) == 256
    assert payload["provider"] == {"allow_fallbacks": True}
    assert payload["questions"]["flag"] == {
        "type": "noul",
        "instructions": "en_us|pre_trigger.truncate|",
    }
    assert payload["questions"]["with_criteria"] == {
        "type": "noul",
        "instructions": "是否紧急",
        "criteria": {"true": "en_us|urgent.true|", "false": "普通事项"},
    }
    assert payload["questions"]["mood"] == {
        "type": "choice",
        "instructions": "en_us|reply.mood.instructions|附加参数",
        "criteria": {"joy": "en_us|reply.mood.criteria.joy|", "none": "无变化", "visual_only": None},
    }
    assert payload["questions"]["level"]["criteria"] == ["en_us|levels.0|", "en_us|levels.1|"]
    assert payload["questions"]["target_box"] == {
        "type": "box",
        "instructions": "en_us|vision.find_cat|",
    }


async def test_build_payload_serializes_dict_state_and_preserves_multimodal_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """业务字典 state 自动序列化为 JSON 字符串；多模态数组保留媒体对象"""
    from nonebot_plugin_decision import lang_ref, noul
    from nonebot_plugin_decision.utils.query import build_payload

    async def fake_text(key: str, _lang_str: str, *_args: Any) -> str:
        return f"resolved:{key}"

    _patch_lang(monkeypatch, AsyncMock(side_effect=fake_text))

    dict_payload = await build_payload(
        {"history_events": "昨天讨论了重构", "latest_events": "今天继续推进"},
        {"still_relevant": noul("是否相关")},
        "zh_hans",
    )
    assert isinstance(dict_payload["state"], str)
    assert json.loads(dict_payload["state"]) == {
        "history_events": "昨天讨论了重构",
        "latest_events": "今天继续推进",
    }

    multimodal_payload = await build_payload(
        [
            lang_ref("prompt.header"),
            {"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}},
        ],
        {"has_cat": noul("图中是否有猫")},
        "zh_hans",
    )
    assert multimodal_payload["state"] == [
        "resolved:prompt.header",
        {"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}},
    ]


def test_resolve_endpoint_handles_openrouter_and_custom_urls() -> None:
    from nonebot_plugin_decision import resolve_endpoint

    assert resolve_endpoint("https://openrouter.ai/api/alpha") == "/decisions"
    assert resolve_endpoint("https://openrouter.ai/api/alpha/") == "/decisions"
    assert resolve_endpoint("https://openrouter.ai/api/alpha/decisions") == "https://openrouter.ai/api/alpha/decisions"
    assert resolve_endpoint("https://api.typesafe.ai/v1") == "/systemone"


def test_parse_answer_accepts_valid_refusal_and_rejects_invalid() -> None:
    from nonebot_plugin_decision import box, choice, noul, score
    from nonebot_plugin_decision.types import BoxAnswer, ChoiceAnswer, NoulAnswer, ScoreAnswer
    from nonebot_plugin_decision.utils.query import _parse_answer

    noul_ans, refused = _parse_answer(noul("x"), {"type": "noul", "noul": 0.7, "confidence": 0.85})
    assert refused is False
    assert isinstance(noul_ans, NoulAnswer)
    assert noul_ans.confidence == pytest.approx(0.85)

    choice_ans, refused = _parse_answer(
        choice("x", criteria={"a": "A"}),
        {"type": "choice", "choice": "a", "confidence": 0.9, "probabilities": {"a": 0.9}},
    )
    assert refused is False
    assert isinstance(choice_ans, ChoiceAnswer)
    assert choice_ans.choice == "a"
    assert choice_ans.confidence == pytest.approx(0.9)

    score_ans, refused = _parse_answer(
        score("x", criteria=["低", "高"]),
        {"type": "score", "score": 1.4, "legend": {"0": "低", "1": "高"}, "confidence": 0.8},
    )
    assert refused is False
    assert isinstance(score_ans, ScoreAnswer)
    assert score_ans.level == 1

    box_ans, refused = _parse_answer(
        box("定位目标"),
        {"type": "box", "box": {"top": 0.1, "bottom": 0.8, "left": 0.2, "right": 0.7}, "confidence": 0.92},
    )
    assert refused is False
    assert isinstance(box_ans, BoxAnswer)
    assert box_ans.box.top == pytest.approx(0.1)

    refusal_ans, refused = _parse_answer(noul("x"), {"type": "refusal"})
    assert refusal_ans is None
    assert refused is True

    # 缺字段 / 类型不对的答案应被拒绝（返回 (None, False) 而不是抛异常）
    assert _parse_answer(noul("x"), {"noul": "不是数字"}) == (None, False)
    assert _parse_answer(noul("x"), {}) == (None, False)
    assert _parse_answer(noul("x"), None) == (None, False)
    assert _parse_answer(choice("x", criteria={}), {"choice": 1}) == (None, False)


async def test_ask_requires_api_key_and_non_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import DecisionError, DecisionNotConfiguredError, ask, noul
    from nonebot_plugin_decision.config import config

    monkeypatch.setattr(config, "decision_api_key", "")
    with pytest.raises(DecisionNotConfiguredError):
        await ask("state", {"q": noul("问题")})

    monkeypatch.setattr(config, "decision_api_key", "test-key")
    with pytest.raises(DecisionError, match="不能为空"):
        await ask("   ", {"q": noul("问题")})


async def test_ask_returns_typed_answers_and_skips_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import ask, noul
    from nonebot_plugin_decision.config import config
    from nonebot_plugin_decision.types import NoulAnswer
    from nonebot_plugin_decision.utils import query as query_module

    monkeypatch.setattr(config, "decision_api_key", "test-key")
    monkeypatch.setattr(config, "decision_base_url", "https://openrouter.ai/api/alpha")
    fake = _FakeClient(
        {
            "answers": {
                "urgent": {"type": "noul", "noul": 0.8, "confidence": 0.9},
                "refused": {"type": "refusal"},
                "broken": {"noul": "bad"},
            },
        },
    )
    monkeypatch.setattr(query_module, "client", fake)

    answers = await ask(
        {"history_events": "A", "latest_events": "B"},
        {
            "urgent": noul("是否紧急"),
            "refused": noul("被拒绝的问题"),
            "broken": noul("坏答案"),
        },
        identify="Test",
        lang_str="zh_hans",
    )

    url, kwargs = fake.calls[0]
    assert url == "/decisions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == config.decision_model
    assert isinstance(kwargs["json"]["state"], str)
    assert isinstance(answers["urgent"], NoulAnswer)
    assert answers["urgent"].noul == pytest.approx(0.8)
    assert "refused" not in answers
    assert "broken" not in answers


async def test_ask_retries_on_network_or_5xx_but_not_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import DecisionError, ask, noul
    from nonebot_plugin_decision.config import config
    from nonebot_plugin_decision.utils import query as query_module

    monkeypatch.setattr(config, "decision_api_key", "test-key")
    monkeypatch.setattr(config, "decision_max_retries", 2)
    monkeypatch.setattr(query_module.asyncio, "sleep", AsyncMock())

    # 网络错误允许重试（首次 + 2 次重试 = 3 次）
    fake_net = _FakeClient(error=httpx.ConnectError("boom"))
    monkeypatch.setattr(query_module, "client", fake_net)
    with pytest.raises(DecisionError):
        await ask("state", {"q": noul("问题")})
    assert len(fake_net.calls) == 3

    # 400 客户端参数错误不重试，且错误文本包含响应体详情
    fake_400 = _FakeClient(status_code=400, text='{"error":{"message":"Invalid state format"}}')
    monkeypatch.setattr(query_module, "client", fake_400)
    with pytest.raises(DecisionError, match="Invalid state format"):
        await ask("state", {"q": noul("问题")})
    assert len(fake_400.calls) == 1


async def test_real_lang_helper_resolves_decision_yaml() -> None:
    """不打桩 lang.text，验证 LangHelper 能从 src/lang/zh_hans/decision.yaml 解析出提示词"""
    from nonebot_plugin_decision import build_payload, choice, lang_ref, noul

    payload = await build_payload(
        {"history_events": "旧对话", "latest_events": "新对话"},
        {
            "still_relevant": noul(lang_ref("context_window.block_relevant")),
            "favor_score": choice(
                lang_ref("reply.favor_score.instructions"),
                criteria={"plus_1": lang_ref("reply.favor_score.criteria.plus_1"), "zero": "不变"},
            ),
        },
        "mlsid::--lang=zh_hans",
    )

    assert "history_events" in payload["questions"]["still_relevant"]["instructions"]
    assert "好感度" in payload["questions"]["favor_score"]["criteria"]["plus_1"]
