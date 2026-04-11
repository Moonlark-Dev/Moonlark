import aiofiles
from nonebot_plugin_localstore import get_config_file


async def get_prompt_text(prompt_type: str, *args, **kwargs) -> str:
    async with aiofiles.open(get_config_file("nonebot_plugin_chat", f"{prompt_type}.txt"), "r", encoding="utf-8") as f:
        return (await f.read()).format(*args, **kwargs)
