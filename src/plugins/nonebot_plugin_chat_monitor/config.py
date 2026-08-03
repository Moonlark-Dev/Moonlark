from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    status_report_password: str = "Moonlark"
    # 消息历史最大返回条数
    chat_monitor_max_messages: int = 500
    # 会话列表最大返回条数
    chat_monitor_max_sessions: int = 200


config = get_plugin_config(Config)
