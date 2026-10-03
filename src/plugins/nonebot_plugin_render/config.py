from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    render_default_theme: str = "default"
    render_viewport: dict = {"width": 500, "height": 10}
    render_cache: bool = True
    # 渲染结果统一转 WebP 的有损质量（0-100）：越大越清晰、体积越大
    render_webp_quality: int = 85


config = get_plugin_config(Config)
