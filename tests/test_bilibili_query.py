"""describe_bilibili_video 的 query 可选参数：工具描述与提示词分支"""

from pathlib import Path
from typing import Any, Optional

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_SCHEMA = REPO_ROOT / "src" / "prompt" / "__tools__" / "describe_bilibili_video.yaml"


async def _get_text(key: str, *_args: object, **_kwargs: object) -> str:
    return key


@pytest.fixture
def bilibili(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """替换网络下载与视频合并，让工具可以离线运行"""
    from nonebot_plugin_chat.utils.tools import bilibili as mod

    async def _fake_get_video_info(_bv_id: str) -> tuple[str, str, str, Optional[str]]:
        return "测试视频", "测试简介", "https://example.com/video", None

    async def _fake_download_file(_url: str, path: Path) -> None:
        path.write_bytes(b"fake-video-bytes")  # ruff: ignore[blocking-path-method-in-async-function]

    monkeypatch.setattr(mod, "VIDEO_DIR", tmp_path)
    monkeypatch.setattr(mod, "_get_video_info", _fake_get_video_info)
    monkeypatch.setattr(mod, "_download_file", _fake_download_file)
    return mod


def _capture(monkeypatch: pytest.MonkeyPatch, mod: Any, result: str = "回答") -> dict:
    captured: dict = {}

    async def _fake_fetch_message(messages: list, identify: str = "", **_kwargs: object) -> str:
        captured["messages"] = messages
        captured["identify"] = identify
        return result

    monkeypatch.setattr(mod, "fetch_message", _fake_fetch_message)
    return captured


def test_tool_schema_declares_optional_query() -> None:
    """工具描述中 query 为可选参数，供 AI 在需要查询细节时填写"""
    schema = yaml.safe_load(TOOL_SCHEMA.read_text(encoding="utf-8"))
    parameters = {param["name"]: param for param in schema["parameters"]}

    assert parameters["bv_id"]["required"] is True
    assert parameters["query"]["required"] is False
    assert parameters["query"]["type"] == "string"


@pytest.mark.asyncio
async def test_query_uses_query_prompt(bilibili: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """提供 query 时走查询提示词，返回查询结果而非视频总结"""
    captured = _capture(monkeypatch, bilibili, result="视频中的配色方案是蓝色")

    result = await bilibili.describe_bilibili_video("BV1xx411c7mD", _get_text, query="视频中的配色方案")

    assert result == "视频中的配色方案是蓝色"
    assert captured["identify"] == "Bilibili Video Query"
    system_prompt = captured["messages"][0]["content"]
    user_prompt = captured["messages"][1]["content"][0]["text"]
    assert "查询" in system_prompt
    assert "测试视频" in user_prompt
    assert "视频中的配色方案" in user_prompt


@pytest.mark.asyncio
async def test_without_query_keeps_summary_prompt(bilibili: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """不提供 query 时保持原有的视频总结行为"""
    captured = _capture(monkeypatch, bilibili, result="视频总结")

    result = await bilibili.describe_bilibili_video("BV1xx411c7mD", _get_text)

    assert result == "视频总结"
    assert captured["identify"] == "Bilibili Video Summary"
    system_prompt = captured["messages"][0]["content"]
    user_prompt = captured["messages"][1]["content"][0]["text"]
    assert "总结" in system_prompt
    assert "请总结这个视频的内容。" in user_prompt


@pytest.mark.asyncio
async def test_query_tool_callable_with_keyword(bilibili: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """工具以关键字参数调用，query 可省略"""
    _capture(monkeypatch, bilibili)
    assert (
        await bilibili.describe_bilibili_video(bv_id="BV1xx411c7mD", get_text=_get_text, query="标题是什么") == "回答"
    )
