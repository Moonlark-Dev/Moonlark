import time
from nonebot_plugin_alconna import Alconna, on_alconna, UniMessage
from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template
from nonebot import get_loaded_plugins
from nonebot_plugin_bots.__main__ import get_bot_status
from nonebot_plugin_bots.config import config
from nonebot_plugin_render.render import generate_render_keys

from .utils import get_system_info, get_nb_uptime

# 记录插件启动时间
start_time = time.time()

lang = LangHelper()

# 创建命令处理器
status_cmd = on_alconna(Alconna("status"))


@status_cmd.handle()
async def handle_status(user_id: str = get_user_id()) -> None:
    """处理 status 命令"""
    # 获取系统信息
    system_info = get_system_info()

    # 获取 Moonlark 运行时间
    nb_uptime = get_nb_uptime(start_time)

    # 获取机器人状态
    bot_status = {}
    for code, user_id in config.bots_list.items():
        bot_status[code] = await get_bot_status(user_id)

    # 获取插件列表
    plugins = [plugin.name for plugin in get_loaded_plugins()]

    # 准备模板数据
    template_data = {
        "system": {**system_info, "nb_uptime": nb_uptime},
        "admin_status": {"nodes": bot_status, "plugins": plugins},
    }

    # 渲染模板并发送
    image = await render_template(
        "status.html.jinja",
        await lang.text("title", user_id),
        user_id,
        template_data,
        await generate_render_keys(
            lang,
            user_id,
            [
                "loadavg",
                "cpu",
                "memory",
                "gb",
                "of",
                "total",
                "swap",
                "online",
                "plugin_count",
                "offline",
                "run_time",
                "uptime",
            ],
            "template."
        ),
    )
    msg = UniMessage().image(raw=image)
    await status_cmd.finish(await msg.export())
