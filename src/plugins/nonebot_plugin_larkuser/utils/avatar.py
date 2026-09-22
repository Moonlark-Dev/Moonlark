from nonebot_plugin_localstore import get_cache_dir
from pathlib import Path
from typing import Optional
import aiofiles
import zlib
import base64

cache_dir = get_cache_dir("nonebot_plugin_larkuser")


def get_encoded_user_id(user_id: str) -> str:
    return base64.b64encode(user_id.encode()).decode()


def get_avatar_file(user_id: str) -> Path:
    return cache_dir.joinpath(f"avatar_{get_encoded_user_id(user_id)}")


async def get_user_avatar(user_id: str) -> Optional[bytes]:
    avatar_file = get_avatar_file(user_id)
    if avatar_file.exists():
        async with aiofiles.open(avatar_file, "rb") as f:
            return zlib.decompress(await f.read())


async def update_user_avatar(user_id: str, avatar: bytes) -> None:
    avatar_file = get_avatar_file(user_id)
    async with aiofiles.open(avatar_file, "wb") as f:
        await f.write(zlib.compress(avatar))


async def is_user_avatar_updated(user_id: str, avatar: bytes) -> bool:
    return avatar != await get_user_avatar(user_id)
