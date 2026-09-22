import json
import aiofiles
from pathlib import Path
from typing import Dict
from nonebot import get_driver

QQ_EMOJI_MAP: Dict[str, str] = {}


@get_driver().on_startup
async def load_qq_emoji_map() -> None:
    """
    异步加载 QQ Emoji 映射表
    """
    global QQ_EMOJI_MAP
    if QQ_EMOJI_MAP:
        return

    resource_path = Path(__file__).parent.parent / "resource" / "qq_emoji.json"

    try:
        async with aiofiles.open(resource_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
            QQ_EMOJI_MAP.update(json.loads(content))
    except Exception as e:
        # 如果加载失败，返回空字典或记录日志
        print(f"Failed to load QQ emoji map: {e}")
