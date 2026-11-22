"""海龟汤插件的回归测试。

覆盖：
1. 指令解析（控制词 / 自由提问 / 无参数）；
2. QQ 官方的快捷按钮：提问是 input、其余是完整指令，且都能被 Alconna 解析；
3. Markdown / 纯文本消息渲染；
4. decision 判定置信度过低或未配置时退回 LLM；
5. 36 小时过期静默清理并恢复 Chat 屏蔽；
6. 正确作答数排行榜的数据查询；
7. Chat 屏蔽登记的可重入与释放。
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def patched_lang_and_prefix(monkeypatch: pytest.MonkeyPatch):
    """替换 LangHelper.text（避免读语言数据库）并固定命令前缀。"""
    from nonebot_plugin_larkutils.command import config as command_config

    monkeypatch.setattr(command_config, "command_start", ["/"])

    from nonebot_plugin_turtle_soup.lang import lang

    async def fake_text(key: str, _user_id: str, *args: object, **_kwargs: object) -> str:
        suffix = "" if not args else "|" + "|".join(str(arg) for arg in args)
        return f"text::{key}{suffix}"

    monkeypatch.setattr(lang, "text", fake_text)


@pytest.fixture(autouse=True)
def clear_games():
    from nonebot_plugin_chat.utils import suppression
    from nonebot_plugin_turtle_soup import game

    game.games.clear()
    suppression._suspenders.clear()  # ruff: ignore[private-member-access] - 测试隔离：清空 Chat 屏蔽登记
    yield
    game.games.clear()
    suppression._suspenders.clear()  # ruff: ignore[private-member-access]


def _puzzle():
    from nonebot_plugin_turtle_soup.types import Puzzle

    return Puzzle(
        title="电梯里的男人",
        puzzle_setting="他每天只乘电梯到7楼，雨天却到10楼。为什么？",
        supplementary_info=["他是侏儒。", "雨天他带着雨伞。"],
        solution="他够不到10楼按钮，雨天用雨伞按。",
    )


# ---------- 指令解析 ----------


def test_parse_input_control_words() -> None:
    from nonebot_plugin_turtle_soup.matcher import parse_input

    assert parse_input(()) == ("", "")
    assert parse_input(("开始", "密室")) == ("start", "密室")
    assert parse_input(("progress",)) == ("progress", "")
    assert parse_input(("提示",)) == ("hint", "")
    assert parse_input(("放弃",)) == ("give-up", "")
    assert parse_input(("rank",)) == ("rank", "")
    assert parse_input(("帮助",)) == ("help", "")


def test_extract_words_handles_bare_command() -> None:
    """裸指令没有 text 参数时不能走参数注入（否则 TypeMisMatch），必须能从 Arparma 取到空元组。"""
    from nonebot_plugin_turtle_soup.matcher import extract_words, turtle_soup

    command = turtle_soup.command()
    bare = command.parse("/turtle-soup")
    assert bare.matched
    assert extract_words(bare) == ()
    with_args = command.parse("/turtle-soup 他是侏儒吗")
    assert with_args.matched
    assert extract_words(with_args) == ("他是侏儒吗",)


def test_parse_input_free_question() -> None:
    from nonebot_plugin_turtle_soup.matcher import parse_input

    assert parse_input(("这个人是故意的吗",)) == ("ask", "这个人是故意的吗")
    assert parse_input(("提问", "他", "是", "人类", "吗")) == ("ask", "他 是 人类 吗")


# ---------- 按钮 ----------


async def test_buttons_are_parseable_and_use_input_for_questions() -> None:
    from nonebot_plugin_turtle_soup.matcher import turtle_soup
    from nonebot_plugin_turtle_soup.messages import home_buttons, in_game_buttons

    command = turtle_soup.command()
    in_game = await in_game_buttons("10")
    assert in_game[0].flag == "input"
    assert in_game[0].text == "/turtle-soup "
    assert {button.flag for button in in_game[1:]} == {"enter"}
    for button in [*in_game, *(await home_buttons("10"))]:
        assert button.text is not None
        assert command.parse(button.text).matched, button.text


async def test_send_rendered_builds_markdown_with_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage
    from nonebot_plugin_turtle_soup.matcher import send_rendered
    from nonebot_plugin_turtle_soup.messages import build_start_message

    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> MagicMock:
        sent.append(self)
        return MagicMock()

    monkeypatch.setattr(UniMessage, "send", fake_send)

    finished = False

    async def fake_finish(*_args: object, **_kwargs: object) -> None:
        nonlocal finished
        finished = True
        raise FinishedException

    matcher = MagicMock()
    matcher.finish = fake_finish
    with pytest.raises(FinishedException):
        await send_rendered(matcher, MagicMock(spec=QQBot), MagicMock(), await build_start_message(_puzzle(), "10"))

    assert finished
    assert len(sent) == 1
    text = next(segment for segment in sent[0] if isinstance(segment, Text))
    assert any("markdown" in styles for styles in text.styles.values())
    keyboard = next(segment for segment in sent[0] if isinstance(segment, Keyboard))
    assert len(keyboard.children) == 4


async def test_build_plain_and_markdown_messages() -> None:
    from nonebot_plugin_turtle_soup.messages import (
        build_ask_message,
        build_end_message,
        build_rank_message,
        build_start_message,
    )
    from nonebot_plugin_turtle_soup.types import EndOutcome

    puzzle = _puzzle()
    start = await build_start_message(puzzle, "10")
    assert puzzle.puzzle_setting in start.plain
    assert "text::label.puzzle" in start.markdown

    ask = await build_ask_message(puzzle, "10", question="他很高吗", answer="不是", percent=30, asked=3)
    assert "他很高吗" in ask.plain
    assert "不是" in ask.plain
    assert "30%" in ask.markdown

    end = await build_end_message(
        EndOutcome(
            solved=True,
            percent=100,
            asked=12,
            title=puzzle.title,
            puzzle_setting=puzzle.puzzle_setting,
            solution=puzzle.solution,
            supplementary_info=puzzle.supplementary_info,
            solved_by="10",
        ),
        "10",
    )
    assert puzzle.solution in end.plain
    assert puzzle.supplementary_info[0] in end.plain
    assert puzzle.solution in end.markdown

    rank = await build_rank_message([("小明", 3), ("小红", 2)], "10", my_index=2, my_count=2)
    assert "小明" in rank.plain
    assert "3" in rank.plain
    assert "text::message.rank_me|2|2" in rank.plain


# ---------- 判定 ----------


async def test_decision_low_confidence_falls_back_to_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import ChoiceAnswer, ScoreAnswer
    from nonebot_plugin_turtle_soup import judge
    from nonebot_plugin_turtle_soup.types import LLMJudgeResponse

    async def fake_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "answer": ChoiceAnswer(choice="yes", confidence=0.1),
            "progress": ScoreAnswer(score=7, confidence=0.9),
        }

    llm_calls = 0

    async def fake_fetch_json(*_args: object, **_kwargs: object) -> LLMJudgeResponse:
        nonlocal llm_calls
        llm_calls += 1
        return LLMJudgeResponse(percent=42, reply="不是")

    monkeypatch.setattr(judge, "ask", fake_ask)
    monkeypatch.setattr(judge, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(judge, "_decision_available", lambda: True)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "decision")

    result = await judge.judge_question(_puzzle(), [], 10, "他很高吗", "10", "qq_10")
    assert llm_calls == 1
    assert result.percent == 42
    assert result.reply == "text::reply.no"
    assert not result.solved


async def test_decision_answer_solves_game(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import ChoiceAnswer, NoulAnswer, ScoreAnswer
    from nonebot_plugin_turtle_soup import judge

    async def fake_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "answer": ChoiceAnswer(choice="yes", confidence=0.9),
            "solved": NoulAnswer(noul=0.95),
            "progress": ScoreAnswer(score=9, confidence=0.9),
        }

    monkeypatch.setattr(judge, "ask", fake_ask)
    monkeypatch.setattr(judge, "_decision_available", lambda: True)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "decision")

    result = await judge.judge_question(_puzzle(), [], 10, "他是够不到按钮吧", "10", "qq_10")
    assert result.solved
    assert result.percent == 100
    assert result.reply == "text::reply.solved"


async def test_decision_progress_accepts_percentage_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """个别模型会把 score 直接给成百分比，不能把它当成第 10 档。"""
    from nonebot_plugin_decision import ChoiceAnswer, NoulAnswer, ScoreAnswer
    from nonebot_plugin_turtle_soup import judge

    async def fake_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "answer": ChoiceAnswer(choice="no", confidence=0.9),
            "solved": NoulAnswer(noul=0.1),
            "progress": ScoreAnswer(score=70, confidence=0.9),
        }

    monkeypatch.setattr(judge, "ask", fake_ask)
    monkeypatch.setattr(judge, "_decision_available", lambda: True)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "decision")

    result = await judge.judge_question(_puzzle(), [], 10, "他很高吗", "10", "qq_10")
    assert result.percent == 70
    assert not result.solved


async def test_low_confidence_solved_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """「是否已经说出汤底」置信度过低时按未解开处理，不能误结束本局。"""
    from nonebot_plugin_decision import ChoiceAnswer, NoulAnswer, ScoreAnswer
    from nonebot_plugin_turtle_soup import judge

    async def fake_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "answer": ChoiceAnswer(choice="yes", confidence=0.9),
            "solved": NoulAnswer(noul=0.99, confidence=0.1),
            "progress": ScoreAnswer(score=9, confidence=0.9),
        }

    monkeypatch.setattr(judge, "ask", fake_ask)
    monkeypatch.setattr(judge, "_decision_available", lambda: True)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "decision")

    result = await judge.judge_question(_puzzle(), [], 10, "他是用伞按的", "10", "qq_10")
    assert not result.solved
    assert result.percent == 90


async def test_decision_without_confidence_field_is_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    """模型不返回 confidence 时按可信处理，不能因为 Pydantic 默认 0.0 每次都退回 LLM。"""
    from nonebot_plugin_decision import ChoiceAnswer, NoulAnswer, ScoreAnswer
    from nonebot_plugin_turtle_soup import judge

    async def fake_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "answer": ChoiceAnswer(choice="no"),
            "solved": NoulAnswer(noul=0.1),
            "progress": ScoreAnswer(score=4),
        }

    async def fail_fetch_json(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("没有 confidence 时不应退回 LLM")

    monkeypatch.setattr(judge, "ask", fake_ask)
    monkeypatch.setattr(judge, "fetch_json", fail_fetch_json)
    monkeypatch.setattr(judge, "_decision_available", lambda: True)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "decision")

    result = await judge.judge_question(_puzzle(), [], 10, "他很高吗", "10", "qq_10")
    assert result.percent == 40
    assert result.reply == "text::reply.no"


async def test_decision_not_configured_uses_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_decision import DecisionNotConfiguredError
    from nonebot_plugin_turtle_soup import judge
    from nonebot_plugin_turtle_soup.types import LLMJudgeResponse

    async def fake_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise DecisionNotConfiguredError("未配置")

    async def fake_fetch_json(*_args: object, **_kwargs: object) -> LLMJudgeResponse:
        return LLMJudgeResponse(percent=20, reply="是")

    monkeypatch.setattr(judge, "ask", fake_ask)
    monkeypatch.setattr(judge, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(judge, "_decision_available", lambda: False)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "decision")

    result = await judge.judge_question(_puzzle(), [], 10, "他在室内吗", "10", "qq_10")
    assert result.percent == 20
    assert result.reply == "text::reply.yes"


async def test_llm_mode_skips_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_turtle_soup import judge
    from nonebot_plugin_turtle_soup.types import LLMJudgeResponse

    async def fail_ask(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("llm 模式不应调用 Decisions API")

    async def fake_fetch_json(*_args: object, **_kwargs: object) -> LLMJudgeResponse:
        return LLMJudgeResponse(percent=55, reply="不重要")

    monkeypatch.setattr(judge, "ask", fail_ask)
    monkeypatch.setattr(judge, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(judge.config, "turtle_soup_judge_mode", "llm")

    result = await judge.judge_question(_puzzle(), [], 10, "天气好吗", "10", "qq_10")
    assert result.percent == 55


def test_percent_only_increases_and_caps_below_100() -> None:
    from nonebot_plugin_turtle_soup.judge import _clamp_percent

    assert _clamp_percent(5, current=30, solved=False) == 30
    assert _clamp_percent(150, current=30, solved=False) == 99
    assert _clamp_percent(150, current=30, solved=True) == 100


# ---------- 过期与排行榜 ----------


async def _make_engine():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nonebot_plugin_turtle_soup.models import TurtleSoupGame, TurtleSoupPlayer

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(TurtleSoupGame.__table__.create)
        await conn.run_sync(TurtleSoupPlayer.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_started_game_persists_and_expires_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_chat.utils.suppression import is_chat_suspended
    from nonebot_plugin_turtle_soup import game as game_module
    from nonebot_plugin_turtle_soup.models import TurtleSoupGame

    _engine, factory = await _make_engine()
    monkeypatch.setattr(game_module, "get_session", lambda **_: factory())

    async def fake_generate(_theme: str):
        return _puzzle()

    monkeypatch.setattr(game_module, "generate_puzzle", fake_generate)
    sent: list[str] = []
    real_resume = game_module.chat_bridge.resume

    def fake_resume(session_id: str) -> None:
        sent.append(session_id)
        real_resume(session_id)

    monkeypatch.setattr(game_module.chat_bridge, "resume", fake_resume)

    game = await game_module.start_game("qq_t1", "10", "电梯")
    assert game.row_id > 0
    assert is_chat_suspended("qq_t1")
    assert game_module.games["qq_t1"] is game

    # 把过期时间改到过去，清理任务应当静默删除并恢复 Chat
    async with factory() as session:
        row = await session.get(TurtleSoupGame, game.row_id)
        assert row is not None
        row.expire_time = datetime.now() - timedelta(seconds=1)
        await session.commit()

    assert await game_module.expire_due_games() == 1
    assert "qq_t1" not in game_module.games
    assert not is_chat_suspended("qq_t1")
    assert sent == ["qq_t1"]

    async with factory() as session:
        remaining = (await session.scalars(game_module.select(TurtleSoupGame))).all()
    assert remaining == []


async def test_finish_publishes_event_and_counts_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    """解开时把汤面与汤底投递给 Chat，并给解出者记一次正确作答。"""
    from nonebot_plugin_turtle_soup import game as game_module

    _engine, factory = await _make_engine()
    monkeypatch.setattr(game_module, "get_session", lambda **_: factory())

    async def fake_generate(_theme: str):
        return _puzzle()

    monkeypatch.setattr(game_module, "generate_puzzle", fake_generate)

    published: list[tuple[str, str, bool, str]] = []

    from nonebot_plugin_turtle_soup.types import Puzzle

    async def fake_publish(
        session_id: str,
        _bot: object,
        _event: object,
        puzzle: Puzzle,
        *,
        user_id: str,
        solved: bool,
    ) -> None:
        published.append((session_id, user_id, solved, puzzle.solution))

    resumed: list[str] = []

    async def fake_drain(_session_id: str) -> None:
        return None

    monkeypatch.setattr(game_module.chat_bridge, "publish_summary", fake_publish)
    monkeypatch.setattr(game_module.chat_bridge, "drain_session", fake_drain)
    monkeypatch.setattr(game_module.chat_bridge, "resume", resumed.append)

    counted: list[str] = []

    async def fake_record(user_id: str) -> None:
        counted.append(user_id)

    monkeypatch.setattr(game_module, "record_correct", fake_record)

    game = await game_module.start_game("qq_t2", "10", "")
    await game.finish(solved=True, solved_by="10002", bot=MagicMock(), event=MagicMock())

    assert published == [("qq_t2", "10002", True, _puzzle().solution)]
    assert counted == ["10002"]
    assert resumed == ["qq_t2"]
    assert "qq_t2" not in game_module.games


async def test_finish_still_resumes_chat_when_publish_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """投递事件失败也不能把会话的 Chat 一直屏蔽下去。"""
    from nonebot_plugin_turtle_soup import game as game_module

    _engine, factory = await _make_engine()
    monkeypatch.setattr(game_module, "get_session", lambda **_: factory())

    async def fake_generate(_theme: str):
        return _puzzle()

    async def broken_publish(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("chat 不可用")

    resumed: list[str] = []

    async def fake_drain(_session_id: str) -> None:
        return None

    monkeypatch.setattr(game_module, "generate_puzzle", fake_generate)
    monkeypatch.setattr(game_module.chat_bridge, "publish_summary", broken_publish)
    monkeypatch.setattr(game_module.chat_bridge, "drain_session", fake_drain)
    monkeypatch.setattr(game_module.chat_bridge, "resume", resumed.append)

    game = await game_module.start_game("qq_t3", "10", "")
    await game.give_up(bot=MagicMock(), event=MagicMock())

    assert resumed == ["qq_t3"]
    assert "qq_t3" not in game_module.games


async def test_concurrent_start_only_one_game(monkeypatch: pytest.MonkeyPatch) -> None:
    """并发开局时唯一索引保证只有一个人真正出题，另一个收到「已有一局」。"""
    import asyncio

    from nonebot_plugin_turtle_soup import game as game_module

    _engine, factory = await _make_engine()
    monkeypatch.setattr(game_module, "get_session", lambda **_: factory())

    async def fake_generate(_theme: str):
        await asyncio.sleep(0.05)
        return _puzzle()

    monkeypatch.setattr(game_module, "generate_puzzle", fake_generate)
    monkeypatch.setattr(game_module.chat_bridge, "suspend", lambda _session_id: None)
    monkeypatch.setattr(game_module.chat_bridge, "resume", lambda _session_id: None)

    results = await asyncio.gather(
        game_module.start_game("qq_t4", "10", ""),
        game_module.start_game("qq_t4", "11", ""),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, BaseException)]
    already = [result for result in results if isinstance(result, game_module.GameAlreadyPlayingError)]
    assert len(successes) == 1
    assert len(already) == 1
    assert "qq_t4" in game_module.games


async def test_next_hint_advances_and_saves(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_turtle_soup import game as game_module

    _engine, factory = await _make_engine()
    monkeypatch.setattr(game_module, "get_session", lambda **_: factory())

    async def fake_generate(_theme: str):
        return _puzzle()

    monkeypatch.setattr(game_module, "generate_puzzle", fake_generate)
    monkeypatch.setattr(game_module.chat_bridge, "suspend", lambda _session_id: None)

    game = await game_module.start_game("qq_t5", "10", "")
    first = await game.next_hint()
    second = await game.next_hint()
    exhausted = await game.next_hint()

    assert first.hint == _puzzle().supplementary_info[0]
    assert first.current == 1
    assert second.hint == _puzzle().supplementary_info[1]
    assert exhausted.finished
    assert exhausted.current == len(_puzzle().supplementary_info)


async def test_ranking_counts_correct_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_turtle_soup import game as game_module
    from nonebot_plugin_turtle_soup import rank as rank_module

    _engine, factory = await _make_engine()
    monkeypatch.setattr(game_module, "get_session", lambda **_: factory())
    monkeypatch.setattr(rank_module, "get_session", lambda **_: factory())

    await game_module.record_correct("10001")
    await game_module.record_correct("10001")
    await game_module.record_correct("10002")

    data = await rank_module.get_ranking_data()
    assert [(item["user_id"], item["data"]) for item in data] == [("10001", 2), ("10002", 1)]


# ---------- 时限与 Chat 屏蔽 ----------


def test_game_expiry_and_question_limit() -> None:
    from nonebot_plugin_turtle_soup.game import Game

    now = datetime.now()
    game = Game(
        row_id=1,
        session_id="qq_t",
        owner_id="10",
        puzzle=_puzzle(),
        history=[],
        percent=0,
        asked=0,
        hint_index=0,
        start_time=now - timedelta(hours=37),
        expire_time=now - timedelta(hours=1),
    )
    assert game.is_expired()
    assert game.deadline_left() <= 0
    game.expire_time = now + timedelta(hours=35)
    assert not game.is_expired()

    game.asked = game.max_questions
    assert not game.can_ask()


async def test_chat_suppression_is_reentrant() -> None:
    from nonebot_plugin_chat.utils.suppression import (
        is_chat_suspended,
        resume_chat,
        suspended_sessions,
        suspend_chat,
    )

    suspend_chat("qq_s", "turtle_soup", "test")
    suspend_chat("qq_s", "other_plugin", "test")
    assert is_chat_suspended("qq_s")
    assert set(suspended_sessions()["qq_s"]) == {"turtle_soup", "other_plugin"}

    resume_chat("qq_s", "turtle_soup")
    assert is_chat_suspended("qq_s")
    resume_chat("qq_s", "other_plugin")
    assert not is_chat_suspended("qq_s")
    assert "qq_s" not in suspended_sessions()


async def test_publish_summary_uses_trigger_mode_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_turtle_soup import chat_bridge

    events: list[tuple[str, str]] = []

    class FakeSession:
        async def add_event(self, prompt: str, trigger_mode: str) -> None:
            events.append((prompt, trigger_mode))

    import nonebot_plugin_chat.core.session as chat_session
    import nonebot_plugin_larkutils.gift_session as gift_session

    def raise_key_error(_session_id: str) -> None:
        raise KeyError(_session_id)

    monkeypatch.setattr(chat_session, "get_session_directly", raise_key_error)

    async def fake_get_or_create(*_args: object, **_kwargs: object) -> FakeSession:
        return FakeSession()

    monkeypatch.setattr(gift_session, "get_or_create_session", fake_get_or_create)

    async def fake_enabled(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr(chat_bridge, "_chat_enabled", fake_enabled)

    await chat_bridge.publish_summary(
        "qq_p",
        MagicMock(),
        MagicMock(),
        _puzzle(),
        user_id="10",
        solved=True,
    )
    assert len(events) == 1
    prompt, trigger_mode = events[0]
    assert trigger_mode == "none"
    assert _puzzle().puzzle_setting in prompt
    assert _puzzle().solution in prompt
