# 启动时初始化表情包感知哈希
import asyncio
from nonebot import get_driver

driver = get_driver()


@driver.on_startup
async def _init_sticker_hashes():
    from .utils.hash_initializer import initialize_sticker_hashes

    await initialize_sticker_hashes()


@driver.on_startup
async def _init_sticker_classifications():
    from .utils.hash_initializer import initialize_sticker_classifications

    # 使用后台任务进行分类，避免阻塞启动流程
    asyncio.create_task(initialize_sticker_classifications())


@driver.on_startup
async def _init_video_server():
    import nonebot
    from fastapi.staticfiles import StaticFiles
    import nonebot_plugin_localstore as store

    VIDEO_DIR = store.get_cache_dir("nonebot_plugin_chat") / "video"
    if not VIDEO_DIR.exists():
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    app = nonebot.get_app()
    app.mount("/chat/video", StaticFiles(directory=VIDEO_DIR), name="chat_video")
