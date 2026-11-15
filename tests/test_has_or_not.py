"""“有无有无” 的题目格式、去重、缓存与判题测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def make_question(
    answer: str = "+",
    contains: tuple[str, str, str] = ("日历", "医院", "键盘"),
    missing: tuple[str, str, str] = ("闹钟", "药店", "鼠标"),
) -> Any:
    """构造一道结构合法的题目。"""
    from nonebot_plugin_has_or_not.types import GeneratedQuestion, PromptPair

    return GeneratedQuestion(
        answer=answer,
        prompts=[PromptPair(contain=contain, missing=miss) for contain, miss in zip(contains, missing, strict=True)],
    )


# ---------- 答案归一化与精确匹配 ----------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("O", "o"),
        ("ｏ", "o"),
        (" 圆形 ", "圆形"),
        ("圆 形", "圆形"),
        ("⭕", "⭕"),
        ("＋", "+"),
    ],
)
def test_normalize_answer_treats_case_width_and_whitespace_as_same(left: str, right: str) -> None:
    from nonebot_plugin_has_or_not.store import normalize_answer

    assert normalize_answer(left) == normalize_answer(right)


def test_normalize_answer_keeps_symbol_answers() -> None:
    from nonebot_plugin_has_or_not.store import normalize_answer

    # 答案本身可能就是特殊符号，归一化不能把标点删掉
    assert normalize_answer("!") == "!"
    assert normalize_answer("?") == "?"


def test_is_exact_match_accepts_symbol_variants_but_not_ball() -> None:
    from nonebot_plugin_has_or_not.store import is_exact_match

    assert is_exact_match("O", "o")
    assert is_exact_match("⭕", "⭕")
    # “球”与“圆形”只是相关，需要交给 Decisions API，精确匹配不能放行
    assert not is_exact_match("球", "圆形")


# ---------- 题目格式 ----------


def test_format_question_matches_required_layout() -> None:
    from nonebot_plugin_has_or_not.store import format_question

    assert format_question(make_question(), escape=False) == ("**有无有无**\n⭕：日历 医院 键盘\n❌：闹钟 药店 鼠标")


def test_format_question_escapes_markdown_when_requested() -> None:
    from nonebot_plugin_has_or_not.store import format_question

    text = format_question(make_question(contains=("*", "医院", "键盘")), escape=True)
    assert "\\*" in text


# ---------- 题目合法性 ----------


def test_valid_question_rejects_answer_appearing_in_words() -> None:
    from nonebot_plugin_has_or_not.store import is_valid_question

    assert is_valid_question(make_question())
    # 规则明确要求答案不能直接出现在词语上
    assert not is_valid_question(make_question(answer="日历"))


def test_valid_question_requires_three_non_empty_pairs() -> None:
    from nonebot_plugin_has_or_not.store import is_valid_question
    from nonebot_plugin_has_or_not.types import GeneratedQuestion, PromptPair

    two_pairs = GeneratedQuestion(
        answer="+",
        prompts=[PromptPair(contain="日历", missing="闹钟"), PromptPair(contain="医院", missing="药店")],
    )
    empty_word = make_question(contains=(" ", "医院", "键盘"))
    assert not is_valid_question(two_pairs)
    assert not is_valid_question(empty_word)


def test_valid_question_rejects_duplicate_words() -> None:
    from nonebot_plugin_has_or_not.store import is_valid_question

    assert not is_valid_question(make_question(contains=("日历", "日历", "键盘")))


# ---------- 去重 ----------


def test_filter_questions_dedupes_answers_and_word_sets() -> None:
    from nonebot_plugin_has_or_not.store import filter_questions

    base = make_question()
    same_answer = make_question(answer="＋")
    same_words = make_question(answer="-")
    different = make_question(
        answer="圆形",
        contains=("轮胎", "盘子", "钟表"),
        missing=("排气管", "杯子", "瓶子"),
    )
    accepted = filter_questions([base, same_answer, same_words, different], [], [])
    assert accepted == [base, different]


def test_filter_questions_uses_recent_history() -> None:
    from nonebot_plugin_has_or_not.store import filter_questions, question_word_signature

    base = make_question()
    assert filter_questions([base], ["+"], []) == []
    assert filter_questions([base], [], [list(question_word_signature(base))]) == []


def test_filter_questions_rejects_near_duplicate_word_sets() -> None:
    from nonebot_plugin_has_or_not.store import filter_questions, question_word_signature

    base = make_question()
    # 只把“鼠标”换成“水杯”：六个词里五个相同，属于短期内重复出题
    near_duplicate = make_question(answer="-", missing=("闹钟", "药店", "水杯"))
    assert filter_questions([near_duplicate], [], [list(question_word_signature(base))]) == []


def test_build_generation_extra_mentions_exclusions_and_count() -> None:
    from nonebot_plugin_has_or_not.store import build_generation_extra

    text = build_generation_extra(["圆形", "+"], [["日历", "医院", "键盘", "闹钟", "药店", "鼠标"]], 20)
    assert "20" in text
    assert "圆形" in text
    assert "+" in text
    assert "JSON 数组" in text


# ---------- 本地缓存 ----------


@pytest.mark.asyncio
async def test_store_persists_and_dedupes_questions(tmp_path: Path) -> None:
    from nonebot_plugin_has_or_not.store import QuestionStore

    path = tmp_path / "questions.json"
    store = QuestionStore(path)
    assert await store.extend([make_question(), make_question(answer="＋")]) == 1
    assert await store.count() == 1

    popped = await store.pop()
    assert popped is not None and popped.answer == "+"
    assert await store.count() == 0

    # 重新读取文件：答案进入近期历史，再写入同一道题会被去重
    reloaded = QuestionStore(path)
    assert await reloaded.extend([make_question()]) == 0
    assert await reloaded.count() == 0
    assert "+" in reloaded.recent_answers


@pytest.mark.asyncio
async def test_store_ensure_ready_only_generates_when_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_has_or_not import store as store_module

    calls: list[tuple[list[str], list[list[str]], int]] = []

    async def fake_generate(exclusions: list[str], word_sets: list[list[str]], count: int) -> list[Any]:
        calls.append((exclusions, word_sets, count))
        return [make_question(answer="正方形", contains=("方桌", "魔方", "田字格"), missing=("圆桌", "球", "井字"))]

    monkeypatch.setattr(store_module, "generate_questions", fake_generate)

    store = store_module.QuestionStore(tmp_path / "questions.json")
    await store.extend([make_question()])
    await store.ensure_ready()
    assert calls == []
    assert await store.count() == 1

    empty = store_module.QuestionStore(tmp_path / "empty.json")
    await empty.ensure_ready()
    assert len(calls) == 1
    assert calls[0][2] == empty.generate_count
    assert await empty.count() == 1


@pytest.mark.asyncio
async def test_store_exclusions_are_passed_to_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_has_or_not import store as store_module

    captured: dict[str, Any] = {}

    async def fake_generate(exclusions: list[str], _word_sets: list[list[str]], _count: int) -> list[Any]:
        captured["exclusions"] = exclusions
        return [make_question(answer="长方形", contains=("门", "书", "手机"), missing=("窗", "笔", "电脑"))]

    monkeypatch.setattr(store_module, "generate_questions", fake_generate)
    store = store_module.QuestionStore(tmp_path / "questions.json")
    await store.extend([make_question()])
    await store.fill()
    assert "+" in captured["exclusions"]


@pytest.mark.asyncio
async def test_generate_questions_requests_question_array(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_has_or_not import store as store_module
    from nonebot_plugin_has_or_not.types import GeneratedQuestion

    question = make_question()
    captured: dict[str, Any] = {}

    async def fake_get_message(role: str, name: str) -> Any:
        return store_module.generate_message(f"{role}:{name}", "system")

    async def fake_fetch_json(messages: list[Any], response_format: Any, **kwargs: Any) -> list[GeneratedQuestion]:
        captured["messages"] = messages
        captured["response_format"] = response_format
        captured["kwargs"] = kwargs
        return [question]

    monkeypatch.setattr(store_module, "get_message", fake_get_message)
    monkeypatch.setattr(store_module, "fetch_json", fake_fetch_json)

    questions = await store_module.generate_questions(["圆形"], [["日历"]], 20)
    assert questions == [question]
    assert len(captured["messages"]) == 2
    assert captured["response_format"] == list[GeneratedQuestion]
    assert captured["kwargs"]["identify"] == "Has Or Not (Generate)"
    assert "圆形" in captured["messages"][1]["content"]


def test_get_question_store_uses_localstore_data_file() -> None:
    from nonebot_plugin_has_or_not.store import get_question_store

    store = get_question_store()
    assert store.path.name == "questions.json"
    assert store.path.parent.name == "nonebot_plugin_has_or_not"


# ---------- 游戏流程 ----------


def test_game_only_owner_can_answer_on_non_qq() -> None:
    from nonebot_plugin_has_or_not.game import HasOrNotGame

    game = HasOrNotGame("session", "owner", object(), object())
    assert game.can_answer("owner")
    assert not game.can_answer("other")


def test_game_allows_everyone_on_qq() -> None:
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot

    from nonebot_plugin_has_or_not.game import HasOrNotGame

    game = HasOrNotGame("session", "owner", create_autospec(QQBot, instance=True), object())
    assert game.can_answer("owner")
    assert game.can_answer("other")


@pytest.mark.asyncio
async def test_game_wrong_guess_decrements_and_correct_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    game.question = make_question("圆形")
    sent: list[str] = []

    async def fake_send(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    async def wrong_judge(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(game, "send_text", fake_send)
    monkeypatch.setattr(game_module.lang, "text", fake_text)
    monkeypatch.setattr(game_module, "judge_guess", wrong_judge)

    await game.handle_guess(game_module.PlayerAction("guess", "user", "球", object()))
    assert game.attempts_left == 9
    assert sent[-1].startswith("game.wrong")

    async def right_judge(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def grant_reward(_user_id: str) -> float:
        return 3.0

    monkeypatch.setattr(game_module, "judge_guess", right_judge)
    monkeypatch.setattr(game, "grant_reward", grant_reward)
    await game.handle_guess(game_module.PlayerAction("guess", "user", "圆", object()))
    assert game.finished
    assert sent[-1].startswith("game.correct")


@pytest.mark.asyncio
async def test_game_wait_action_times_out_after_idle() -> None:
    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    game.last_activity = 0.0
    assert await game.wait_action() is None


@pytest.mark.asyncio
async def test_game_wait_action_returns_queued_action() -> None:
    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    action = game_module.PlayerAction("guess", "user", "圆形", object())
    game.queue.put_nowait(action)
    assert await game.wait_action() is action


# ---------- 判题 ----------


@pytest.mark.asyncio
async def test_judge_uses_exact_match_without_calling_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_has_or_not import judge as judge_module

    async def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("精确匹配不应调用 Decisions API")

    monkeypatch.setattr(judge_module, "ask", fail)
    assert await judge_module.judge_guess("O", "o", "user") is True


@pytest.mark.asyncio
async def test_judge_accepts_semantic_match_from_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import NoulAnswer
    from nonebot_plugin_has_or_not import judge as judge_module

    async def fake_text(key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return {"judge.instructions": "判断", "judge.true": "相同", "judge.false": "不同"}[key]

    async def fake_ask(state: Any, _questions: Any, **kwargs: Any) -> dict[str, Any]:
        assert state == {"answer": "圆形", "guess": "o"}
        assert kwargs["identify"] == "Has Or Not (Judge)"
        return {"same": NoulAnswer(noul=0.92)}

    monkeypatch.setattr(judge_module.lang, "text", fake_text)
    monkeypatch.setattr(judge_module, "ask", fake_ask)
    assert await judge_module.judge_guess("o", "圆形", "user") is True

    async def low_probability(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"same": NoulAnswer(noul=0.1)}

    monkeypatch.setattr(judge_module, "ask", low_probability)
    assert await judge_module.judge_guess("球", "圆形", "user") is False


@pytest.mark.asyncio
async def test_judge_falls_back_to_exact_match_when_decision_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nonebot_plugin_decision import DecisionNotConfiguredError
    from nonebot_plugin_has_or_not import judge as judge_module

    async def fake_text(_key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return ""

    async def raise_not_configured(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise DecisionNotConfiguredError("未配置")

    monkeypatch.setattr(judge_module.lang, "text", fake_text)
    monkeypatch.setattr(judge_module, "ask", raise_not_configured)
    assert await judge_module.judge_guess("球", "圆形", "user") is False
