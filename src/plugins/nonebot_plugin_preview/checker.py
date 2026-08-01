from urllib.parse import urlparse

from nonebot_plugin_chat.utils.url_validator import resolve_internal

from .exceptions import AccessDenied


def check_url_protocol(url: str) -> bool:
    parsed_url = urlparse(url)
    if parsed_url.scheme == "file":
        raise AccessDenied
    return bool(parsed_url.scheme)


async def check_url_access(url: str) -> None:
    if await resolve_internal(urlparse(url)):
        raise AccessDenied
