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


@driver.on_startup
async def _init_file_server():
    import nonebot
    from fastapi.staticfiles import StaticFiles
    import nonebot_plugin_localstore as store

    FILE_DIR = store.get_cache_dir("nonebot_plugin_chat") / "files"
    if not FILE_DIR.exists():
        FILE_DIR.mkdir(parents=True, exist_ok=True)

    app = nonebot.get_app()
    app.mount("/chat/files", StaticFiles(directory=FILE_DIR), name="chat_files")


import nonebot
from fastapi import Query
from .utils.blog import get_blog_posts

app = nonebot.get_app()


@app.get("/chat/blog")
async def blog_list(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
):
    return await get_blog_posts(page=page, page_size=page_size)


@driver.on_startup
async def _init_moonlark_main():
    from .core.ego.moonlark_main import init_moonlark_main, moonlark_main
    from nonebot_plugin_apscheduler import scheduler

    await init_moonlark_main()

    @scheduler.scheduled_job("interval", minutes=5, id="moonlark_main_wake_check")
    async def _wake_check():
        """每 5 分钟检查是否是刚醒来，触发计划生成"""
        if moonlark_main.state["sleep_mode"]:
            return
        # 清醒且困倦度低于唤醒阈值时触发计划生成（每天首次，0:00 重置标志）
        sc = moonlark_main.sleep_controller
        if sc.tiredness < 0.35 and hasattr(sc, "_morning_plan_scheduled") is False:
            sc._morning_plan_scheduled = True
            import asyncio

            asyncio.create_task(moonlark_main.run_morning_plan())

    @scheduler.scheduled_job("cron", hour=0, minute=0, id="moonlark_main_clear_plan_flag")
    async def _clear_plan_flag():
        moonlark_main.sleep_controller._morning_plan_scheduled = False

    @scheduler.scheduled_job("cron", hour=3, id="moonlark_main_cleanup_plans")
    async def _cleanup_plans():
        from .core.ego.planner import Planner

        Planner.cleanup_expired_plans()
