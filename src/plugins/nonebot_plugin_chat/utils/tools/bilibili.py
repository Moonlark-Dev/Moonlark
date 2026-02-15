from nonebot_plugin_openai.utils.message import generate_message
from bilibili_api import video
from ...config import config
import httpx
from nonebot_plugin_openai import fetch_message
from nonebot import logger, require
import asyncio
import os
from pathlib import Path
from typing import Optional, Tuple

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

# 获取缓存目录
VIDEO_DIR = store.get_cache_dir("nonebot_plugin_chat") / "video"
if not VIDEO_DIR.exists():
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


async def _get_video_info(bv_id: str) -> Tuple[str, str, str, Optional[str]]:
    """获取视频信息和下载地址"""
    v = video.Video(bvid=bv_id)
    info = await v.get_info()
    title = info["title"]
    desc = info["desc"]

    play_url = await v.get_download_url(page_index=0)
    video_url = None
    audio_url = None

    if "dash" in play_url:
        video_streams = play_url["dash"]["video"]
        video_streams.sort(key=lambda x: x["bandwidth"])
        video_url = video_streams[0]["baseUrl"]

        if "audio" in play_url["dash"]:
            audio_streams = play_url["dash"]["audio"]
            audio_streams.sort(key=lambda x: x["bandwidth"])
            audio_url = audio_streams[0]["baseUrl"]

    elif "durl" in play_url:
        video_url = play_url["durl"][0]["url"]

    if not video_url:
        raise ValueError("无法获取视频下载地址")

    return title, desc, video_url, audio_url


async def _download_file(url: str, path: Path) -> None:
    """下载文件"""
    headers = {
        "Referer": "https://www.bilibili.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)


async def _merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """合并视频和音频"""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"FFmpeg merge failed: {stderr.decode()}")
        raise RuntimeError("FFmpeg merge failed")


async def describe_bilibili_video(bv_id: str) -> str:
    """
    根据 BV 号总结 B 站视频内容
    """
    file_name = f"{bv_id}.mp4"
    file_path = VIDEO_DIR / file_name
    temp_video_path = VIDEO_DIR / f"{bv_id}_temp_video.mp4"
    temp_audio_path = VIDEO_DIR / f"{bv_id}_temp_audio.m4a"

    try:
        title, desc, video_url, audio_url = await _get_video_info(bv_id)

        await _download_file(video_url, temp_video_path)

        if audio_url:
            await _download_file(audio_url, temp_audio_path)
            try:
                await _merge_video_audio(temp_video_path, temp_audio_path, file_path)
            except RuntimeError:
                # 合并失败，回退到仅视频
                if file_path.exists():
                    os.remove(file_path)
                os.rename(temp_video_path, file_path)
        else:
            if file_path.exists():
                os.remove(file_path)
            os.rename(temp_video_path, file_path)

        external_url = f"{config.moonlark_api_base}/chat/video/{file_name}"

        messages = [
            generate_message("你是一个视频内容分析助手。请根据提供的视频，总结视频的主要内容。", role="system"),
            generate_message(
                [
                    {"type": "text", "text": f"这是 B 站视频：{title}\n简介：{desc}\n请总结这个视频的内容。"},
                    {"type": "video_url", "video_url": {"url": external_url}},
                ],
                role="user",
            ),
        ]

        result = await fetch_message(messages=messages, identify="Bilibili Video Summary")

        if file_path.exists():
            os.remove(file_path)

        return result

    finally:
        if temp_video_path.exists():
            os.remove(temp_video_path)
        if temp_audio_path.exists():
            os.remove(temp_audio_path)
