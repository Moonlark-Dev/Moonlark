"""render 插件把渲染结果统一转成 WebP 的回归测试

背景：此前 render_template 提供 resize 参数，对 PNG 做 75% 缩放（resize_png_to_75_percent），
只有签到插件启用。现在改为渲染完成后统一转 WebP，用有损编码换更小的体积。
"""

from io import BytesIO

from PIL import Image


def _make_png(width: int = 120, height: int = 60, mode: str = "RGB") -> bytes:
    image = Image.new(mode, (width, height), (255, 0, 0, 255) if mode == "RGBA" else (255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_convert_image_to_webp_outputs_webp() -> None:
    """转换结果应真的是 WebP（用 RIFF....WEBP 魔数判断，而非只看后缀名）"""
    from nonebot_plugin_render.render import convert_image_to_webp

    result = convert_image_to_webp(_make_png())

    assert result.startswith(b"RIFF")
    assert result[8:12] == b"WEBP"
    with Image.open(BytesIO(result)) as image:
        assert image.format == "WEBP"
        assert image.size == (120, 60)


def test_convert_image_to_webp_keeps_size_and_alpha() -> None:
    """不再做 75% 缩放：尺寸必须原样保留，带透明通道的图也不能丢 alpha"""
    from nonebot_plugin_render.render import convert_image_to_webp

    result = convert_image_to_webp(_make_png(200, 100, mode="RGBA"))

    with Image.open(BytesIO(result)) as image:
        assert image.size == (200, 100)
        assert "A" in image.convert("RGBA").getbands()


def test_convert_image_to_webp_smaller_than_png() -> None:
    """体积应小于原 PNG，否则这次改造就没有意义"""
    import random

    from nonebot_plugin_render.render import convert_image_to_webp

    random.seed(0)
    image = Image.new("RGB", (300, 300))
    image.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(300 * 300)])
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()

    assert len(convert_image_to_webp(png)) < len(png)


def test_convert_image_to_webp_respects_quality() -> None:
    """quality 参数应真的传给编码器：低质量产物应明显小于高质量产物"""
    import random

    from nonebot_plugin_render.render import convert_image_to_webp

    random.seed(1)
    image = Image.new("RGB", (400, 400))
    image.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(400 * 400)])
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()

    assert len(convert_image_to_webp(png, quality=10)) < len(convert_image_to_webp(png, quality=85))


def test_render_template_no_longer_accepts_resize() -> None:
    """resize 机制应被彻底移除，避免调用方继续传这个已失效的参数"""
    import inspect

    from nonebot_plugin_render.render import render_template

    assert "resize" not in inspect.signature(render_template).parameters
