from nonebot_plugin_openai.utils.message import generate_message
from bilibili_api import video
from ...config import config
import httpx
from nonebot_plugin_openai import fetch_message
from nonebot import logger, require
import asyncio
import os

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

# 获取缓存目录
VIDEO_DIR = store.get_cache_dir("nonebot_plugin_chat") / "video"
if not VIDEO_DIR.exists():
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


async def describe_bilibili_video(bv_id: str) -> str:
    """
    根据 BV 号总结 B 站视频内容
    """
    # 文件路径
    file_name = f"{bv_id}.mp4"
    file_path = VIDEO_DIR / file_name
    temp_video_path = VIDEO_DIR / f"{bv_id}_temp_video.mp4"
    temp_audio_path = VIDEO_DIR / f"{bv_id}_temp_audio.m4a"

    try:
        # 获取视频信息
        v = video.Video(bvid=bv_id)
        info = await v.get_info()
        title = info["title"]
        desc = info["desc"]

        # 获取视频下载地址
        play_url = await v.get_download_url(page_index=0)

        video_url = None
        audio_url = None

        if "dash" in play_url:
            # 优先选择清晰度较低的视频流以减小体积
            video_streams = play_url["dash"]["video"]
            # 按 bandwidth 排序，取最小的
            video_streams.sort(key=lambda x: x["bandwidth"])
            video_url = video_streams[0]["baseUrl"]
            
            # 获取音频流
            if "audio" in play_url["dash"]:
                audio_streams = play_url["dash"]["audio"]
                # 按 bandwidth 排序，取最小的
                audio_streams.sort(key=lambda x: x["bandwidth"])
                audio_url = audio_streams[0]["baseUrl"]
                
        elif "durl" in play_url:
            video_url = play_url["durl"][0]["url"]

        if not video_url:
            return "无法获取视频下载地址"

        # 使用 httpx 下载，伪造 Referer
        headers = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }

        async with httpx.AsyncClient() as client:
            # 下载视频流
            resp = await client.get(video_url, headers=headers)
            with open(temp_video_path, "wb") as f:
                f.write(resp.content)
            
            # 下载音频流（如果有）
            if audio_url:
                resp = await client.get(audio_url, headers=headers)
                with open(temp_audio_path, "wb") as f:
                    f.write(resp.content)

        # 合并视频和音频
        if audio_url:
            # 使用 ffmpeg 合并
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y", # 覆盖输出文件
                "-i", str(temp_video_path),
                "-i", str(temp_audio_path),
                "-c:v", "copy",
                "-c:a", "aac",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg merge failed: {stderr.decode()}")
                # 如果合并失败，回退到只使用视频流（重命名临时视频文件）
                if temp_video_path.exists():
                    if file_path.exists():
                        os.remove(file_path)
                    os.rename(temp_video_path, file_path)
        else:
            # 没有音频流，直接重命名视频文件
            if file_path.exists():
                os.remove(file_path)
            os.rename(temp_video_path, file_path)

        # 构建外部访问 URL
        external_url = f"{config.moonlark_api_base}/chat/video/{file_name}"

        # 构造 OpenAI 请求
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
        
        # 处理完成后删除生成的合并视频
        if file_path.exists():
            os.remove(file_path)
            
        return result

    finally:
        # 清理临时文件
        if temp_video_path.exists():
            os.remove(temp_video_path)
        if temp_audio_path.exists():
            os.remove(temp_audio_path)
