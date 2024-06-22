from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    render_default_theme: str = "base/default.html.jinja"
    render_viewport: dict = {"width": 500, "height": 10}

config = get_plugin_config(Config)
