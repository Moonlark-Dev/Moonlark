from urllib.parse import urlparse

from .exceptions import AccessDenied


def check_url_protocol(url):
    parsed_url = urlparse(url)
    if parsed_url.scheme == "file":
        raise AccessDenied
    return bool(parsed_url.scheme)
