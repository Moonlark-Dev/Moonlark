from pathlib import Path
import inspect
from types import ModuleType
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from nonebot import get_plugin_by_module_name
from nonebot_plugin_htmlrender import html_to_pic
from nonebot_plugin_orm import get_session
from nonebot_plugin_larklang.__main__ import get_user_language, LangHelper
from nonebot_plugin_larkutils import parse_special_user_id
from .lang import lang
from .config import config
from .cache import get_cache
from . import theme
from os import getcwd

from PIL import Image
import io

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
        return None
    plugin = get_plugin_by_module_name(module.__name__)
    if plugin is None:
        return None
    return plugin.name


def resize_png_to_75_percent(png_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(png_bytes)) as img:
        new_size = (int(img.width * 0.75), int(img.height * 0.75))
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)

        output_buffer = io.BytesIO()
        resized_img.save(output_buffer, format="PNG")
        return output_buffer.getvalue()


async def generate_render_keys(
    helper: LangHelper, user_id: str, keys: list[str], key_prefix: str = ""
) -> dict[str, str]:
    k = {}
    for key in keys:
        k[key.split(".")[-1]] = await helper.text(f"{key_prefix}{key}", user_id)
    return k


async def render_template(
    name: str,
    title: str,
    user_id: str,
    templates: dict,
    keys: dict[str, str] = {},
    cache: bool = False,
    resize: bool = False,
    viewport: dict | None = None,
) -> bytes:
    if user_id.startswith("mlsid::") and parse_special_user_id(user_id).get("ignore-cache", "n") == "y":
        cache = False
    module = inspect.getmodule(inspect.stack()[1][0])
    plugin_name = get_plugin_name(module) or "nonebot-plugin-render"
    footer = await lang.text("render.footer", user_id, plugin_name)
    t, base = await get_base(user_id)
    async with get_session() as session:
        if cache and (c := await get_cache(name, await get_user_language(user_id, session), t)):
            return c
    if keys:
        templates = templates | {"text": keys}
    image = await html_to_pic(
        await render_template_to_text(name, title, footer, templates, base),
        template_path=Path(getcwd()).joinpath(f"src/templates").as_uri(),
        viewport=viewport or config.render_viewport,
    )
    if resize:
        return resize_png_to_75_percent(image)
    return image
