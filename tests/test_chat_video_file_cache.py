"""视频文件缓存（cache/nonebot_plugin_chat/files）的清理行为

覆盖一类问题：``describe_video`` 改用 base64 内联上传 AI 之后，
``files/`` 目录里的视频副本（``video_*``）与下载临时文件（``temp_*``）
都不再有人使用，但旧实现既不清理副本、临时文件在异常路径上也可能残留，
导致该目录随视频解析次数无限增长（生产备份 ``files/video_*.mp4`` 堆积）。
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


async def _ready_file_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Any):
    """导入 file 模块，初始化描述缓存，并把缓存目录指向本次测试专属的 tmp_path

    FILE_CACHE_DIR 默认指向共享的真实缓存目录，直接读它会让测试互相污染。
    """
    from nonebot_plugin_chat.utils import file as file_module

    cache_dir = tmp_path / "files"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(file_module, "FILE_CACHE_DIR", cache_dir)
    await file_module._()
    return file_module


def _fake_video_segment(name: str = "clip.mp4", url: str = "https://example.com/clip.mp4") -> MagicMock:
    segment = MagicMock()
    segment.name = name
    segment.url = url
    segment.id = None
    return segment


def _fake_event() -> MagicMock:
    event = MagicMock()
    event.get_user_id.return_value = "123456"
    return event


async def test_describe_video_leaves_no_video_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """describe_video 不应再往 files/ 目录复制视频副本"""
    file_module = await _ready_file_module(monkeypatch, tmp_path)
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"0" * 256)

    monkeypatch.setattr(file_module, "fetch_message", AsyncMock(return_value="一只猫在跳舞"))
    monkeypatch.setattr(file_module, "get_message", AsyncMock(return_value={"role": "system", "content": "system"}))
    monkeypatch.setattr(file_module, "get_message_text", AsyncMock(return_value="title=movie description="))

    result = await file_module.describe_video(video, "movie.mp4", "123456")

    assert result == "一只猫在跳舞"
    assert list(file_module.FILE_CACHE_DIR.glob("video_*")) == [], "describe_video 不应再向 files/ 目录写入视频副本"


async def test_temp_file_is_cleaned_when_download_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """下载失败时下载临时文件也必须被清理，不能残留"""
    file_module = await _ready_file_module(monkeypatch, tmp_path)

    async def broken_download(url: str, path: Any) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(file_module, "_download_file", broken_download)

    file_type, file_name, description = await file_module.get_file_summary(
        _fake_video_segment(), _fake_event(), MagicMock(), {}
    )

    assert file_type == "video"
    assert description == "无法获取视频文件"
    assert list(file_module.FILE_CACHE_DIR.glob("temp_*")) == [], "下载失败后临时文件残留"


async def test_stale_temp_file_is_not_reused(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """上次下载中断留下的残档不能被当作缓存的下载结果复用"""
    file_module = await _ready_file_module(monkeypatch, tmp_path)
    url = "https://example.com/stalehash16hex"
    file_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    stale_path = file_module.FILE_CACHE_DIR / f"temp_{file_hash}.mp4"
    stale_path.write_bytes(b"corrupt partial data")

    async def no_download(download_url: str, path: Any) -> None:
        pass  # 模拟永远下载不出文件

    monkeypatch.setattr(file_module, "_download_file", no_download)
    monkeypatch.setattr(file_module, "describe_video", AsyncMock(return_value="描述"))

    file_type, file_name, description = await file_module.get_file_summary(
        _fake_video_segment(name="clip.mp4", url=url), _fake_event(), MagicMock(), {}
    )

    # 旧实现发现 temp 已存在就跳过下载，直接把残档交给 describe_video；新实现先删除残档
    assert description == "描述"
    describe_video_calls = file_module.describe_video.call_args_list
    assert describe_video_calls, "下载后应调用 describe_video"
    assert describe_video_calls[0][0][0] == stale_path
    assert not stale_path.exists(), "残档不应被复用，调用 describe_video 前应已重新下载"
    assert list(file_module.FILE_CACHE_DIR.glob("temp_*")) == [], "临时文件用完应清理"


def _fake_session_with_lock(locked: bool) -> MagicMock:
    """构造一个只带 openai_messages.fetcher_lock 状态的最小会话"""
    session = MagicMock()
    session.processor.openai_messages.fetcher_lock.locked.return_value = locked
    return session


async def test_cleanup_job_skips_when_session_is_processing(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """有会话正在处理（fetcher_lock 被占用）时，清理任务应当跳过，不动任何文件"""
    from nonebot_plugin_chat.core.session import groups as groups_registry

    file_module = await _ready_file_module(monkeypatch, tmp_path)
    temp_file = file_module.FILE_CACHE_DIR / "temp_leftover.mp4"
    temp_file.write_bytes(b"x")

    groups_registry.clear()
    groups_registry["qq_occupied"] = _fake_session_with_lock(locked=True)
    try:
        await file_module._cleanup_file_cache()
        assert temp_file.exists(), "有会话处理中时不应清理缓存文件"
    finally:
        groups_registry.pop("qq_occupied", None)


async def test_cleanup_job_removes_leftovers(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """定时清理任务应删除 files/ 目录中残留的 temp_* 与旧版 video_* 文件"""
    from nonebot_plugin_chat.core.session import groups as groups_registry

    file_module = await _ready_file_module(monkeypatch, tmp_path)
    temp_file = file_module.FILE_CACHE_DIR / "temp_leftover.mp4"
    video_file = file_module.FILE_CACHE_DIR / "video_0123456789abcdef.mp4"
    other_file = file_module.FILE_CACHE_DIR / "keep_me.txt"
    temp_file.write_bytes(b"x")
    video_file.write_bytes(b"y")
    other_file.write_bytes(b"z")

    # 全量跑套件时其他测试可能往 groups 留下带状态的会话，清理行为不应被它们影响
    sessions_backup = dict(groups_registry)
    groups_registry.clear()
    try:
        await file_module._cleanup_file_cache()
    finally:
        groups_registry.update(sessions_backup)

    assert not temp_file.exists()
    assert not video_file.exists()
    assert other_file.exists(), "不属于缓存清理模式的文件不应被删除"
