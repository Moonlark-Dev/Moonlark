from pathlib import Path
import inspect
from types import ModuleType
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from nonebot import get_plugin_by_module_name
from nonebot_plugin_htmlrender import html_to_pic

from ..nonebot_plugin_larklang.__main__ import get_user_language
from .lang import lang
from .config import config
from .cache import get_cache
from . import theme
from os import getcwd

file_loader = FileSystemLoader(Path("./src/templates"))
env = Environment(
    loader=file_loader,
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    enable_async=True,
)


async def get_base(user_id: str) -> tuple[str, str]:
    return (t := await theme.get_user_theme(user_id)), await theme.get_theme_file(t)


async def render_template_to_text(
    template_name: str, title: str, footer: str, kwargs: dict, base: str = config.render_default_theme
) -> str:
    template = env.get_template(template_name)
    return await template.render_async(main_title=title, footer=footer, base=base, **kwargs)


def get_plugin_name(module: ModuleType | None) -> Optional[str]:
    if module is None:
        return
    plugin = get_plugin_by_module_name(module.__name__)
    if plugin is None:
        return
    return plugin.name


async def render_template(name: str, title: str, user_id: str, templates: dict, cache: bool = False) -> bytes:
    module = inspect.getmodule(inspect.stack()[1][0])
    plugin_name = get_plugin_name(module) or "nonebot-plugin-render"
    footer = await lang.text("render.footer", user_id, plugin_name)
    t, base = await get_base(user_id)
    if cache and (c := await get_cache(name, await get_user_language(user_id), t)):
        return c
    return await html_to_pic(
        await render_template_to_text(name, title, footer, templates, base),
        template_path=Path(getcwd()).joinpath(f"src/templates").as_uri(),
        viewport=config.render_viewport,
    )
