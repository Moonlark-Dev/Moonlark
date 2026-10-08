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


def convert_image_to_webp(image_bytes: bytes, quality: int = config.render_webp_quality) -> bytes:
    """把渲染结果转成 WebP，用体积更小的编码替代此前的 PNG 缩放一刀切

    Args:
        image_bytes: 浏览器截图产出的图片二进制（通常为 PNG）
        quality: 有损 WebP 质量（0-100），越大越清晰、体积越大

    Returns:
        WebP 格式的图片二进制
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        # WebP 不支持调色板/部分特殊模式，统一转到 RGB(A) 后再编码
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="WEBP", quality=quality, method=4)
        return output_buffer.getvalue()


async def generate_render_keys(
    helper: LangHelper, user_id: str, keys: list[str], key_prefix: str = ""
) -> dict[str, str]:
    k = {}
    for key in keys:
        k[key.split(".")[-1]] = await helper.text(f"{key_prefix}{key}", user_id)
    return k


DEFAULT_BACKGROUND_URL = "https://www.dmoe.cc/random.php"


async def render_template(
    name: str,
    title: str,
    user_id: str,
    templates: dict,
    *,
    keys: dict[str, str] = {},
    cache: bool = False,
    viewport: dict | None = None,
    background_url: str = DEFAULT_BACKGROUND_URL,
) -> bytes:
    """渲染模板为图片。

    除前四个参数外全部为 keyword-only：此前可选参数按位置传递，删除 `resize`
    参数后调用方原来的 `cache=True, resize=True` 悄悄变成 `cache=True, viewport=True`，
    布尔值被当成 viewport 交给 playwright（`viewport: expected object, got boolean`），
    渲染整体失败。改为 keyword-only 后，同类错位会立刻抛 TypeError 而不是静默换义。
    """
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
    templates["background_url"] = background_url
    image = await html_to_pic(
        await render_template_to_text(name, title, footer, templates, base),
        template_path=Path(getcwd()).joinpath(f"src/templates").as_uri(),
        viewport=viewport or config.render_viewport,
    )
    return convert_image_to_webp(image)
