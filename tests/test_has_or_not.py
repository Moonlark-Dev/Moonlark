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


def test_format_question_table_matches_qq_markdown_table_layout() -> None:
    from nonebot_plugin_has_or_not.store import format_question_table

    expected = (
        "| ⭕ 有 | ❌ 无 |\n"
        "| ----------- | ----------- |\n"
        "| 日历 | 闹钟 |\n"
        "| 医院 | 药店 |\n"
        "| 键盘 | 鼠标 |"
    )
    assert format_question_table(make_question(), escape=False) == expected


def test_format_question_table_escapes_markdown_and_pipe_in_cells() -> None:
    from nonebot_plugin_has_or_not.store import format_question_table

    text = format_question_table(make_question(contains=("*", "a|b", "键盘")), escape=True)
    lines = text.splitlines()
    assert lines[0] == "| ⭕ 有 | ❌ 无 |"
    assert lines[1] == "| ----------- | ----------- |"
    assert lines[2] == "| \\* | 闹钟 |"
    assert lines[3] == "| a\\|b | 药店 |"


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

    judged_calls: list[tuple[str, Any, str]] = []

    async def wrong_judge(guess: str, question: Any, user_id: str) -> bool:
        judged_calls.append((guess, question, user_id))
        return False

    monkeypatch.setattr(game, "send_text", fake_send)
    monkeypatch.setattr(game, "send_result", fake_send)
    monkeypatch.setattr(game_module.lang, "text", fake_text)
    monkeypatch.setattr(game_module, "judge_guess", wrong_judge)

    await game.handle_guess(game_module.PlayerAction("user", "球", object()))
    assert game.attempts_left == 9
    assert sent[-1].startswith("game.wrong")
    assert judged_calls == [("球", game.question, "user")]

    async def right_judge(guess: str, question: Any, user_id: str) -> bool:
        judged_calls.append((guess, question, user_id))
        return True

    async def grant_reward(_user_id: str) -> float:
        return 3.0

    monkeypatch.setattr(game_module, "judge_guess", right_judge)
    monkeypatch.setattr(game, "grant_reward", grant_reward)
    await game.handle_guess(game_module.PlayerAction("user", "圆", object()))
    assert game.finished
    assert sent[-1].startswith("game.correct")
    assert judged_calls[-1] == ("圆", game.question, "user")


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
    action = game_module.PlayerAction("user", "圆形", object())
    game.queue.put_nowait(action)
    assert await game.wait_action() is action


@pytest.mark.asyncio
async def test_game_reveal_now_ends_immediately_and_cancels_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """按下「查看答案」时在处理器里直接结算，并取消仍在等待的游戏循环。"""
    import asyncio

    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    game.question = make_question("圆形")
    game_module.games["session"] = game
    sent: list[str] = []

    async def fake_send_result(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    async def never_finishes() -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(game, "send_result", fake_send_result)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    task = asyncio.create_task(never_finishes())
    game.task = task
    await game.reveal_now()

    assert game.finished
    assert "session" not in game_module.games
    assert sent == ["game.reveal_manual:('圆形',)"]
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_game_reveal_now_before_question_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """题目还在生成时按「查看答案」也要给出明确回应并结束本局。"""
    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    game_module.games["session"] = game
    sent: list[str] = []

    async def fake_send_result(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    monkeypatch.setattr(game, "send_result", fake_send_result)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    await game.reveal_now()

    assert game.finished
    assert "session" not in game_module.games
    assert sent == ["game.reveal_before_question:()"]


@pytest.mark.asyncio
async def test_game_reveal_now_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """重复按「查看答案」（早先消息上的按钮）不会重复公布答案。"""
    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    game.question = make_question("圆形")
    sent: list[str] = []

    async def fake_send_result(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return f"{key}:{args}"

    monkeypatch.setattr(game, "send_result", fake_send_result)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    await game.reveal_now()
    await game.reveal_now()

    assert len(sent) == 1


@pytest.mark.asyncio
async def test_qq_question_message_uses_markdown_table_and_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方发题时使用 Markdown 表格展示，并附带作答、查看答案、规则说明按钮。"""
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Keyboard, Text
    from nonebot_plugin_has_or_not import game as game_module
    from nonebot_plugin_has_or_not.store import format_question_table

    labels = {
        "button.guess": "作答",
        "button.reveal": "查看答案",
        "button.rules": "规则说明",
    }

    async def fake_text(key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return labels[key]

    monkeypatch.setattr(game_module.lang, "text", fake_text)

    game = game_module.HasOrNotGame("session", "owner", create_autospec(QQBot, instance=True), object())
    game.question = make_question(
        answer="会发光",
        contains=("台灯", "萤火虫", "路灯"),
        missing=("书架", "蚯蚓", "电线杆"),
    )
    message = await game.build_question_message()
    assert message is not None

    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == format_question_table(game.question)
    assert any("markdown" in styles for styles in text.styles.values())

    buttons = next(seg for seg in message if isinstance(seg, Keyboard)).children
    assert [(button.flag, str(button.label), button.text) for button in buttons] == [
        ("input", "作答", "/has-or-not "),
        ("enter", "查看答案", "/has-or-not 查看答案"),
        ("enter", "规则说明", "/has-or-not 规则说明"),
    ]


@pytest.mark.asyncio
async def test_qq_result_message_has_again_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方猜对或结束公布结果时附带「再来一局」按钮，正文按 markdown 转义。"""
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Keyboard, Text
    from nonebot_plugin_has_or_not import game as game_module
    from nonebot_plugin_larkutils import escape_markdown

    async def fake_text(_key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return "再来一局"

    monkeypatch.setattr(game_module.lang, "text", fake_text)

    game = game_module.HasOrNotGame("session", "owner", create_autospec(QQBot, instance=True), object())
    for result in (
        "🎉 猜对了！答案是「+」，获得 3 VimCoin。",
        "已查看答案，游戏结束。答案是「+」。",
    ):
        message = await game.build_result_message(result)

        text = next(seg for seg in message if isinstance(seg, Text))
        assert text.text == escape_markdown(result)
        assert any("markdown" in styles for styles in text.styles.values())

        buttons = next(seg for seg in message if isinstance(seg, Keyboard)).children
        assert [(button.flag, str(button.label), button.text) for button in buttons] == [
            ("enter", "再来一局", "/has-or-not"),
        ]


@pytest.mark.asyncio
async def test_qq_generate_failed_uses_result_with_again_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """出题失败结束本局时也走 send_result，在 QQ 官方下提供「再来一局」按钮。"""
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_has_or_not import game as game_module

    class BrokenStore:
        async def count(self) -> int:
            return 1

        async def ensure_ready(self) -> None:
            raise RuntimeError("generation failed")

    results: list[str] = []

    async def fake_send_result(text: str) -> None:
        results.append(text)

    async def fake_text(key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return f"{key}"

    game = game_module.HasOrNotGame("session", "owner", create_autospec(QQBot, instance=True), object())
    monkeypatch.setattr(game_module, "get_question_store", lambda: BrokenStore())
    monkeypatch.setattr(game, "send_result", fake_send_result)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    await game.run()

    assert game.finished
    assert results == ["game.generate_failed"]


@pytest.mark.asyncio
async def test_qq_rules_message_switches_buttons_by_game_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方查看规则说明：局内附带作答/查看答案按钮，局外附带开始一局按钮。"""
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Keyboard, Text
    from nonebot_plugin_has_or_not import game as game_module

    texts = {
        "game.rules": "纯文本规则",
        "game.rules_markdown": "### 「有无有无」规则说明",
        "button.start": "开始一局",
        "button.guess": "作答",
        "button.reveal": "查看答案",
    }

    async def fake_text(key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return texts[key]

    monkeypatch.setattr(game_module.lang, "text", fake_text)
    qq_bot = create_autospec(QQBot, instance=True)

    idle_msg = await game_module.build_rules_message(qq_bot, "user", None)
    idle_text = next(seg for seg in idle_msg if isinstance(seg, Text))
    assert idle_text.text == "### 「有无有无」规则说明"
    assert any("markdown" in styles for styles in idle_text.styles.values())
    idle_buttons = next(seg for seg in idle_msg if isinstance(seg, Keyboard)).children
    assert [(button.flag, str(button.label), button.text) for button in idle_buttons] == [
        ("enter", "开始一局", "/has-or-not"),
    ]

    active_game = game_module.HasOrNotGame("session", "owner", qq_bot, object())
    in_game_msg = await game_module.build_rules_message(qq_bot, "user", active_game)
    in_game_buttons = next(seg for seg in in_game_msg if isinstance(seg, Keyboard)).children
    assert [(button.flag, str(button.label), button.text) for button in in_game_buttons] == [
        ("input", "作答", "/has-or-not "),
        ("enter", "查看答案", "/has-or-not 查看答案"),
    ]

    non_qq_msg = await game_module.build_rules_message(object(), "user", active_game)
    assert non_qq_msg.extract_plain_text() == "纯文本规则"
    assert not any(isinstance(seg, Keyboard) for seg in non_qq_msg)


@pytest.mark.asyncio
async def test_qq_result_falls_back_to_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """带键盘的结算消息发送失败时，回退纯文本，避免按键看起来毫无回应。"""
    from unittest.mock import create_autospec

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_has_or_not import game as game_module

    class BrokenMessage:
        async def send(self, **_kwargs: Any) -> None:
            raise RuntimeError("send failed")

    sent: list[str] = []

    async def fake_build(_text: str) -> Any:
        return BrokenMessage()

    async def fake_send_text(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return "发送 /has-or-not 可以再来一局。"

    game = game_module.HasOrNotGame("session", "owner", create_autospec(QQBot, instance=True), object())
    monkeypatch.setattr(game, "build_result_message", fake_build)
    monkeypatch.setattr(game, "send_text", fake_send_text)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    await game.send_result("游戏结束。答案是「+」。")

    assert sent == ["游戏结束。答案是「+」。\n发送 /has-or-not 可以再来一局。"]


@pytest.mark.asyncio
async def test_non_qq_result_appends_again_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """其它适配器没有键盘，结算消息末尾附上再来一局的指令提示。"""
    from nonebot_plugin_has_or_not import game as game_module

    game = game_module.HasOrNotGame("session", "owner", object(), object())
    sent: list[str] = []

    async def fake_send_text(text: str) -> None:
        sent.append(text)

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return "发送 /has-or-not 可以再来一局。"

    monkeypatch.setattr(game, "send_text", fake_send_text)
    monkeypatch.setattr(game_module.lang, "text", fake_text)

    await game.send_result("游戏结束。答案是「+」。")

    assert sent == ["游戏结束。答案是「+」。\n发送 /has-or-not 可以再来一局。"]


def test_reveal_keywords_accept_end_game_words() -> None:
    from nonebot_plugin_has_or_not.game import REVEAL_KEYWORDS

    assert {"查看答案", "结束游戏", "结束本局"} <= REVEAL_KEYWORDS


def test_plain_keyword_rule_matches_reveal_and_rules() -> None:
    """按键指令丢掉前缀时，直接发送中文关键词也能被兜底识别。"""
    from nonebot_plugin_has_or_not.matcher import _is_plain_keyword

    class FakeEvent:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_plaintext(self) -> str:
            return self._text

    assert _is_plain_keyword(FakeEvent("查看答案"))
    assert _is_plain_keyword(FakeEvent(" 结束游戏 "))
    assert _is_plain_keyword(FakeEvent("规则说明"))
    assert not _is_plain_keyword(FakeEvent("圆形"))
    assert not _is_plain_keyword(FakeEvent("/has-or-not 查看答案"))


# ---------- 判题 ----------


@pytest.mark.asyncio
async def test_judge_uses_exact_match_and_rejects_prompt_words_without_calling_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nonebot_plugin_has_or_not import judge as judge_module

    async def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("本地可直接判定时不应调用 Decisions API")

    monkeypatch.setattr(judge_module, "ask", fail)
    question = make_question(
        answer="o",
        contains=("轮胎", "盘子", "钟表"),
        missing=("排气管", "杯子", "瓶子"),
    )
    assert await judge_module.judge_guess("O", question, "user") is True
    assert await judge_module.judge_guess("   ", question, "user") is False
    # 直接照搬题面词语不应通过，也不需要请求 Decisions API
    assert await judge_module.judge_guess("轮胎", question, "user") is False
    assert await judge_module.judge_guess("排气管", question, "user") is False


@pytest.mark.asyncio
async def test_judge_passes_question_rules_and_reference_answer_to_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nonebot_plugin_decision import NoulAnswer
    from nonebot_plugin_has_or_not import judge as judge_module

    light_question = make_question(
        answer="会发光",
        contains=("台灯", "萤火虫", "路灯"),
        missing=("书架", "蚯蚓", "电线杆"),
    )

    async def fake_text(key: str, _user_id: str, *_args: Any, **_kwargs: Any) -> str:
        return {
            "judge.rules": "有无有无玩法规则",
            "judge.instructions": "结合规则与参考答案判断是否符合规则",
            "judge.true": "符合规则或本质特征一致",
            "judge.false": "不符合规则",
        }[key]

    seen_guesses: list[str] = []

    async def fake_ask(state: Any, questions: Any, **kwargs: Any) -> dict[str, Any]:
        seen_guesses.append(state["guess"])
        assert state == {
            "rules": "有无有无玩法规则",
            "question": {
                "contains": ["台灯", "萤火虫", "路灯"],
                "missing": ["书架", "蚯蚓", "电线杆"],
                "pairs": [
                    {"contain": "台灯", "missing": "书架"},
                    {"contain": "萤火虫", "missing": "蚯蚓"},
                    {"contain": "路灯", "missing": "电线杆"},
                ],
            },
            "reference_answer": "会发光",
            "guess": state["guess"],
        }
        assert kwargs["identify"] == "Has Or Not (Judge)"
        question_spec = questions["correct"]
        assert question_spec.type == "noul"
        assert question_spec.instructions == "结合规则与参考答案判断是否符合规则"
        assert question_spec.criteria == {
            "true": "符合规则或本质特征一致",
            "false": "不符合规则",
        }
        return {"correct": NoulAnswer(noul=0.92)}

    monkeypatch.setattr(judge_module.lang, "text", fake_text)
    monkeypatch.setattr(judge_module, "ask", fake_ask)
    for equivalent_guess in ("光", "发光", "光源"):
        assert await judge_module.judge_guess(equivalent_guess, light_question, "user") is True
    assert seen_guesses == ["光", "发光", "光源"]

    async def low_probability(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"correct": NoulAnswer(noul=0.1)}

    monkeypatch.setattr(judge_module, "ask", low_probability)
    circle_question = make_question(
        answer="圆形",
        contains=("轮胎", "盘子", "钟表"),
        missing=("排气管", "杯子", "瓶子"),
    )
    assert await judge_module.judge_guess("球", circle_question, "user") is False


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
    circle_question = make_question(
        answer="圆形",
        contains=("轮胎", "盘子", "钟表"),
        missing=("排气管", "杯子", "瓶子"),
    )
    assert await judge_module.judge_guess("球", circle_question, "user") is False


@pytest.mark.asyncio
async def test_real_lang_helper_resolves_has_or_not_judge_prompts() -> None:
    """不打桩 lang.text，验证 src/lang/zh_hans/has_or_not.yaml 中判题提示词能正常解析。"""
    from nonebot_plugin_decision import build_payload, noul
    from nonebot_plugin_has_or_not.judge import build_judge_state
    from nonebot_plugin_has_or_not.lang import lang
    from nonebot_plugin_larklang.__main__ import load_languages

    await load_languages()
    user_id = "mlsid::--lang=zh_hans"
    rules = await lang.text("judge.rules", user_id)
    instructions = await lang.text("judge.instructions", user_id)
    true_text = await lang.text("judge.true", user_id)
    false_text = await lang.text("judge.false", user_id)

    for resolved in (rules, instructions, true_text, false_text):
        assert resolved
        assert not resolved.startswith("[缺失:")

    assert "有无有无" in rules
    assert "reference_answer" in instructions
    assert "会发光" in true_text
    assert "光源" in true_text
    assert "用电" in false_text

    question = make_question(
        answer="会发光",
        contains=("台灯", "萤火虫", "路灯"),
        missing=("书架", "蚯蚓", "电线杆"),
    )
    payload = await build_payload(
        build_judge_state(question, "发光", rules),
        {"correct": noul(instructions, true=true_text, false=false_text)},
        "zh_hans",
    )
    assert "台灯" in payload["state"]
    assert "会发光" in payload["state"]
    assert payload["questions"]["correct"]["criteria"]["true"] == true_text
    assert payload["questions"]["correct"]["criteria"]["false"] == false_text


@pytest.mark.asyncio
async def test_real_lang_helper_resolves_has_or_not_rules_and_buttons() -> None:
    """验证规则说明文案（纯文本与 Markdown 表格版）及按钮文案能由 LangHelper 正常格式化。"""
    from nonebot_plugin_has_or_not.lang import lang
    from nonebot_plugin_larklang.__main__ import load_languages

    await load_languages()
    user_id = "mlsid::--lang=zh_hans"

    details = await lang.text("help.details", user_id)
    rules_plain = await lang.text("game.rules", user_id, 10, "3")
    rules_markdown = await lang.text("game.rules_markdown", user_id, 10, "3")
    again_label = await lang.text("button.again", user_id)
    start_label = await lang.text("button.start", user_id)

    for resolved in (details, rules_plain, rules_markdown, again_label, start_label):
        assert resolved
        assert not resolved.startswith("[缺失:")

    assert again_label == "再来一局"
    assert start_label == "开始一局"
    assert "会发光" in rules_plain
    assert "10" in rules_plain
    assert "3 VimCoin" in rules_plain
    assert "| ⭕ 有 | ❌ 无 |" in rules_markdown
    assert "| ----------- | ----------- |" in rules_markdown
    assert "10" in rules_markdown
    assert "3 VimCoin" in rules_markdown
    assert "<" not in rules_markdown
    assert ">" not in rules_markdown
