"""ask_ai 工具：完全异步执行、复用相同查询、以事件汇报结果"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

if TYPE_CHECKING:
    from nonebot_plugin_chat.utils.ai_agent import AskAISession

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAT_LANG = REPO_ROOT / "src" / "lang" / "zh_hans" / "chat.yaml"


class _FakeSession:
    """只记录 add_event 的调用；可选地让 add_event 抛错以验证兜底路径

    target/bot 与真实 BaseSession 一致，挂载在 session 上（直接补发消息时要用到）。
    """

    def __init__(self, fail_add_event: bool = False) -> None:
        self.events: list[tuple[str, str]] = []
        self.fail_add_event = fail_add_event
        self.target = object()
        self.bot = object()

    async def add_event(self, event_prompt: str, trigger_mode: str = "probability") -> None:
        if self.fail_add_event:
            raise RuntimeError("消息队列不可用")
        self.events.append((event_prompt, trigger_mode))


@dataclass
class _FakeProcessor:
    session: _FakeSession


class _Sent:
    """UniMessage 的替身：send() 时把文本记录到共享列表"""

    def __init__(self, text: str, sink: list[str]) -> None:
        self._text = text
        self._sink = sink

    async def send(self, *_args: Any, **_kwargs: Any) -> None:
        self._sink.append(self._text)


class _FakeToolManager:
    """text() 直接返回带占位符的模板，processor 指向假会话"""

    def __init__(self, session: _FakeSession | None) -> None:
        self.processor = None if session is None else cast("Any", _FakeProcessor(session))
        self.calls: list[tuple[str, tuple]] = []
        self.fail_render = False

    async def text(self, key: str, *args: Any) -> str:
        self.calls.append((key, args))
        if key == "ask_ai.accepted":
            return "已受理"
        # 只让结果/失败模板渲染失败，受理提示仍然正常
        if self.fail_render:
            raise RuntimeError("文案渲染失败")
        if key == "ask_ai.result_prompt":
            return f"结果<{args[0]}>"
        return f"失败<{args[0]}>"


def _make_agent(session: _FakeSession | None = None) -> tuple["AskAISession", _FakeToolManager]:
    from nonebot_plugin_chat.utils.ai_agent import AskAISession

    manager = _FakeToolManager(session)
    agent = AskAISession("user", cast("Any", manager))
    # 跳过 select_tools（它需要真实的 processor）
    agent.functions = [cast("Any", object())]
    return agent, manager


async def test_ask_ai_returns_immediately_without_waiting() -> None:
    """ask_ai 立即返回受理提示，结果的产出完全由后台任务负责"""
    session = _FakeSession()
    agent, _manager = _make_agent(session)
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_fetch(_query: str) -> str:
        started.set()
        await release.wait()
        return "研究结论"

    agent.fetch_answer = _slow_fetch  # type: ignore[method-assign]

    result = await agent.ask_ai("量子计算最新进展")

    # 未等待 fetch 完成就已返回受理提示
    assert result == "已受理"
    assert not release.is_set()
    await asyncio.wait_for(started.wait(), timeout=1)
    assert session.events == []

    release.set()
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)

    # 结果以 trigger_mode="all" 的事件汇报
    assert ("结果<量子计算最新进展>", "all") in session.events


async def test_ask_ai_reuses_running_task_for_same_query() -> None:
    """同一个 query 在完成前重复调用不会重复起任务"""
    session = _FakeSession()
    agent, _manager = _make_agent(session)
    release = asyncio.Event()
    fetch_calls = 0

    async def _slow_fetch(_query: str) -> str:
        nonlocal fetch_calls
        fetch_calls += 1
        await release.wait()
        return "结论"

    agent.fetch_answer = _slow_fetch  # type: ignore[method-assign]

    await agent.ask_ai("同一个问题")
    first_task = agent.tasks["同一个问题"]
    await agent.ask_ai("同一个问题")

    # 复用同一个任务，任务在阻塞中（未完成），因而不会被 done_callback 清掉
    assert agent.tasks["同一个问题"] is first_task
    assert not first_task.done()

    release.set()
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)
    # 只抓取了一次：第二次调用没有另起任务
    assert fetch_calls == 1


async def test_ask_ai_starts_new_task_for_different_query() -> None:
    """不同 query 各自并发执行"""
    session = _FakeSession()
    agent, _manager = _make_agent(session)
    release = asyncio.Event()

    async def _slow_fetch(query: str) -> str:
        await release.wait()
        return query

    agent.fetch_answer = _slow_fetch  # type: ignore[method-assign]

    await agent.ask_ai("问题 A")
    await agent.ask_ai("问题 B")

    assert set(agent.tasks) == {"问题 A", "问题 B"}
    release.set()
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)


async def test_failed_query_reports_failure_event() -> None:
    """后台任务失败时同样以事件汇报失败信息"""
    session = _FakeSession()
    agent, _manager = _make_agent(session)

    async def _boom(_query: str) -> str:
        raise RuntimeError("工具调用失败")

    agent.fetch_answer = _boom  # type: ignore[method-assign]

    await agent.ask_ai("会失败的问题")
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)

    assert len(session.events) == 1
    prompt, trigger_mode = session.events[0]
    assert trigger_mode == "all"
    assert prompt.startswith("失败<会失败的问题>")


async def test_task_is_removed_after_completion() -> None:
    """任务结束后从登记表中移除，之后同样的 query 可以重新发起"""
    session = _FakeSession()
    agent, _manager = _make_agent(session)

    async def _fast_fetch(query: str) -> str:
        return query

    agent.fetch_answer = _fast_fetch  # type: ignore[method-assign]

    await agent.ask_ai("问题")
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)
    # done_callback 在事件循环下一轮才执行
    await asyncio.sleep(0)

    assert agent.tasks == {}


async def test_report_skipped_when_processor_missing() -> None:
    """processor 未设置时不汇报，且不抛异常"""
    agent, _manager = _make_agent(session=None)

    async def _fast_fetch(query: str) -> str:
        return query

    agent.fetch_answer = _fast_fetch  # type: ignore[method-assign]

    await agent.ask_ai("问题")
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)


async def test_result_sent_directly_when_event_queue_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件入队失败时，结果改为直接补发消息，不会静默丢失"""
    session = _FakeSession(fail_add_event=True)
    agent, _manager = _make_agent(session)

    async def _fast_fetch(query: str) -> str:
        return query

    agent.fetch_answer = _fast_fetch  # type: ignore[method-assign]

    sent: list[str] = []

    async def _fake_send(self: Any, *_args: Any, **_kwargs: Any) -> None:
        sent.append(str(self))

    # 在消费方模块的导入点替换，UniMessage 是包装类，直接 patch 其 send 对实例不生效
    from nonebot_plugin_chat.utils import ai_agent as ai_agent_module

    monkeypatch.setattr(ai_agent_module, "UniMessage", lambda text: _Sent(text, sent))

    await agent.ask_ai("问题")
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)

    assert session.events == []
    assert sent == ["结果<问题>"]


async def test_result_reported_when_lang_render_fails() -> None:
    """文案渲染失败时退回原始数据，仍然以事件汇报"""
    session = _FakeSession()
    agent, manager = _make_agent(session)
    manager.fail_render = True

    async def _fast_fetch(_query: str) -> str:
        return "研究结论"

    agent.fetch_answer = _fast_fetch  # type: ignore[method-assign]

    await agent.ask_ai("问题")
    await asyncio.wait_for(asyncio.gather(*agent.tasks.values()), timeout=1)

    assert len(session.events) == 1
    prompt, trigger_mode = session.events[0]
    assert trigger_mode == "all"
    assert "问题" in prompt
    assert "研究结论" in prompt


def test_lang_keys_exist_and_format() -> None:
    """受理提示与结果/失败模板存在，且占位符数量与调用方式一致"""
    ask_ai = yaml.safe_load(CHAT_LANG.read_text(encoding="utf-8"))["ask_ai"]

    assert "processing" not in ask_ai
    assert ask_ai["accepted"].format() == ask_ai["accepted"]
    assert "问题" in ask_ai["result_prompt"].format("问题", "结论")
    assert "结论" in ask_ai["result_prompt"].format("问题", "结论")
    assert "错误" in ask_ai["failed_prompt"].format("问题", "错误")
