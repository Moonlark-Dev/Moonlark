import base64

from ..config import config


def get_authorization_header() -> dict[str, str]:
    """
    获取 authorization 头内容
    :return: 头
    """
    token = base64.b64encode(config.wakatime_api_key.encode()).decode()
    return {"Authorization": f"Basic {token}"}
