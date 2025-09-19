from nonebot import get_plugin_config
from pydantic import BaseModel

class Config(BaseModel):
    """Plugin Config Here"""

    cave_need_review: bool = False
    cave_user_cd: float = 10.0
    cave_maximum_similarity: float = 0.75
    cave_restore_date: int = 7
    cave_message_list_length: int = 20

config = get_plugin_config(Config)
