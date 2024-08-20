from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    render_default_theme: str = "default"
    render_viewport: dict = {"width": 500, "height": 10}
    render_cache: bool = True


config = get_plugin_config(Config)
