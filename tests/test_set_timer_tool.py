"""set_timer 工具：参数契约、描述与返回的确认信息"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_SCHEMA = REPO_ROOT / "src" / "prompt" / "__tools__" / "set_timer.yaml"
CHAT_LANG = REPO_ROOT / "src" / "lang" / "zh_hans" / "chat.yaml"


def test_timer_set_lang_key_accepts_two_placeholders() -> None:
    """新增的确认文案存在，且能接受触发时间与定时器描述两个参数"""
    prompt = yaml.safe_load(CHAT_LANG.read_text(encoding="utf-8"))["prompt"]

    assert "timer_set" in prompt
    rendered = prompt["timer_set"].format("2026-09-19 10:00", "提醒小明交作业")
    assert "2026-09-19 10:00" in rendered
    assert "提醒小明交作业" in rendered


def test_tool_schema_requires_delay_and_description() -> None:
    """delay 与 description 都是必填参数，且带类型说明"""
    schema = yaml.safe_load(TOOL_SCHEMA.read_text(encoding="utf-8"))
    parameters = {param["name"]: param for param in schema["parameters"]}

    assert set(parameters) == {"delay", "description"}
    assert parameters["delay"]["required"] is True
    assert parameters["delay"]["type"] == "integer"
    assert parameters["description"]["required"] is True
    assert parameters["description"]["type"] == "string"


def test_tool_description_documents_trigger_behaviour() -> None:
    """工具描述需要说明触发时的行为，以及 description 要写成完整指令"""
    description = yaml.safe_load(TOOL_SCHEMA.read_text(encoding="utf-8"))["description"]

    # 触发时会注入「计时器 <description> 已触发」并强制回复
    assert "已触发" in description
    assert "强制" in description
    # 定时器一次性、绑定当前会话
    assert "一次性" in description
    # description 必须写成留给未来自己的完整指令
    assert "未来" in description
    # 描述文本会被 .format(emoji_table=...) 处理，不能包含花括号
    assert "{" not in description
    assert "}" not in description


async def test_set_timer_registers_timer_and_returns_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    """set_timer 写入数据库并向模型返回包含触发时间的确认信息"""
    from nonebot_plugin_chat.core.session.base import BaseSession

    added: list = []

    class _FakeDBSession:
        def add(self, obj: object) -> None:
            added.append(obj)

        async def commit(self) -> None:
            pass

    class _FakeSessionCM:
        async def __aenter__(self) -> "_FakeDBSession":
            return _FakeDBSession()

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    monkeypatch.setattr("nonebot_plugin_chat.core.session.base.get_session", _FakeSessionCM)

    async def _fake_text(key: str, *args: object, **_kwargs: object) -> str:
        return ":".join([key, *(str(arg) for arg in args)])

    # set_timer 只依赖 session_id / llm_timers / text，用最小替身直接调用未绑定方法
    session = SimpleNamespace(session_id="qq_10000", llm_timers=[], text=_fake_text)

    result = await BaseSession.set_timer(session, delay=10, description="提醒小明交作业")

    assert result.startswith("prompt.timer_set:")
    assert "提醒小明交作业" in result
    assert len(session.llm_timers) == 1
    assert session.llm_timers[0]["description"] == "提醒小明交作业"
    assert added
    assert added[0].description == "提醒小明交作业"
    assert added[0].session_id == "qq_10000"
