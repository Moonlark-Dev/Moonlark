from typing import Awaitable, Callable, Optional

import aiofiles
import hashlib
from nonebot import get_driver
from nonebot.log import logger
from nonebot_plugin_localstore import get_cache_dir
from nonebot_plugin_larklang.__main__ import get_languages

from .config import config
from .theme import get_themes

CACHE_CREATOR_TYPE = Callable[[str], Awaitable[bytes]]
creator_functions: dict[str, CACHE_CREATOR_TYPE] = {}
cache_dir = get_cache_dir("nonebot-plugin-render")


def creator(template_name: str):
    def d(func: CACHE_CREATOR_TYPE) -> CACHE_CREATOR_TYPE:
        creator_functions[template_name] = func
        return func

    return d


def clear_cache() -> None:
    """删除上一次运行留下的缓存文件

    模板内容随版本变化，旧缓存不能继续使用；同时避免上一次运行写到一半的
    文件被当成有效缓存读出来。
    """
    for file in cache_dir.iterdir():
        if file.is_file():
            file.unlink()


async def setup_cache() -> None:
    """按 模板 × 语言 × 主题 预渲染缓存

    单个组合渲染失败只跳过该组合，不影响其余缓存，也不会中断机器人启动。
    """
    languages = list(get_languages().keys())
    themes = list((await get_themes()).keys())
    created = 0
    for template, function in creator_functions.items():
        for lang in languages:
            for theme in themes:
                try:
                    image = await function(f"mlsid::--lang={lang};--theme={theme};--ignore-cache=y")
                except Exception:
                    logger.opt(exception=True).warning(f"Render 缓存预渲染失败，跳过 {template=} {lang=} {theme=}")
                    continue
                if not image:
                    logger.warning(f"Render 缓存预渲染返回空数据，跳过 {template=} {lang=} {theme=}")
                    continue
                f_name = hashlib.sha256(
                    f"mlrc::--template={template};--lang={lang};--theme={theme}".encode(),
                ).hexdigest()
                async with aiofiles.open(cache_dir.joinpath(f_name), "wb") as f:
                    await f.write(image)
                created += 1
                logger.debug(f"成功为 {template=} {lang=} {theme=} 创建 Render 缓存！")
    logger.success(f"Render 缓存创建完成，共 {created} 个！")


async def warm_up_cache() -> None:
    """后台预热入口：预渲染失败只记日志，不影响后续渲染与机器人运行"""
    try:
        await setup_cache()
    except Exception:
        logger.opt(exception=True).warning("Render 缓存预热失败，后续渲染将回退到实时渲染")


def start_cache_warm_up() -> None:
    """把预热放进后台任务，不阻塞启动

    预热要真渲染每个 creator 的 模板 × 语言 × 主题（帮助面板单张就要数秒），
    同步等待会明显拖慢启动。任务是 lifespan task group 的子任务，停止时会随
    任务组一起取消。
    """
    logger.info("正在后台创建 Render 缓存...")
    get_driver().task_group.start_soon(warm_up_cache)


@get_driver()._lifespan.on_ready
async def prepare_cache() -> None:
    """启动阶段清空旧缓存，并在后台重建

    此前缓存挂在 ``on_bot_connect`` 上创建：多账号进程里第一个 bot 连接时
    ``len(get_bots())`` 恰为 1，缓存会被生成；第二个 bot 连接时 ``len(get_bots())``
    变成 2，于是先把刚生成的缓存删掉、再跳过重建——进程里从此只有空缓存。

    这里挂在 lifespan 的 ready 阶段而不是 ``on_startup``：预热函数依赖的插件数据
    （例如 ``nonebot_plugin_larkhelp`` 的 ``help_list``）本身也在 ``on_startup``
    里初始化，而钩子按插件加载顺序执行，本插件的钩子会排在它们前面。nonebot 的
    ``Lifespan.startup()`` 先跑完所有 ``on_startup`` 钩子再跑 ready 钩子，所以
    ready 阶段既在启动时、又保证各插件的数据已经就绪。
    """
    clear_cache()
    if not config.render_cache:
        logger.info("Render 缓存已关闭（RENDER_CACHE=false），跳过预热")
        return
    start_cache_warm_up()


async def get_cache(template: str, lang: str, theme: str) -> Optional[bytes]:
    f_name = hashlib.sha256(f"mlrc::--template={template};--lang={lang};--theme={theme}".encode()).hexdigest()
    path = cache_dir.joinpath(f_name)
    if path.exists():
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
    return None
