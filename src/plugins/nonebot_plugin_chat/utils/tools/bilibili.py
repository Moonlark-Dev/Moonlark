from nonebot_plugin_openai.utils.message import generate_message
from bilibili_api import video
from ...config import config
import httpx
from nonebot_plugin_openai import fetch_message
from nonebot import logger, require

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
    try:
        # 获取视频信息
        v = video.Video(bvid=bv_id)
        info = await v.get_info()
        title = info['title']
        desc = info['desc']
        
        # 获取视频下载地址
        play_url = await v.get_download_url(page_index=0)
        
        video_url = None
        if 'dash' in play_url:
            # 优先选择清晰度较低的视频流以减小体积
            video_streams = play_url['dash']['video']
            # 按 bandwidth 排序，取最小的
            video_streams.sort(key=lambda x: x['bandwidth'])
            video_url = video_streams[0]['baseUrl']
        elif 'durl' in play_url:
            video_url = play_url['durl'][0]['url']
        
        if not video_url:
            return "无法获取视频下载地址"
        
        # 下载视频
        file_name = f"{bv_id}.mp4"
        file_path = VIDEO_DIR / file_name
        
        # 使用 httpx 下载，伪造 Referer
        headers = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(video_url, headers=headers)
            with open(file_path, "wb") as f:
                f.write(resp.content)
                
        # 构建外部访问 URL
        external_url = f"{config.moonlark_api_base}/chat/video/{file_name}"
        
        # 构造 OpenAI 请求
        messages = [
            generate_message("你是一个视频内容分析助手。请根据提供的视频，总结视频的主要内容。", role="system"),
            generate_message([
                {"type": "text", "text": f"这是 B 站视频：{title}\n简介：{desc}\n请总结这个视频的内容。"},
                {"type": "video_url", "video_url": {"url": external_url}}
            ], role="user")
        ]
        
        result = await fetch_message(
            messages=messages,
            identify="Bilibili Video Summary"
        )
        return result

    except Exception as e:
        logger.exception(e)
        return f"处理视频时发生错误: {str(e)}"
