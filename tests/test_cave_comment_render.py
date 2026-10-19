import io

from PIL import Image


def _view(**kwargs):
    view = {"nickname": "Aster", "time": "2026-04-13 12:00:00", "id": "(1)", "text": "你好"}
    view.update(kwargs)
    return view


def _decode(raw: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(raw))
    image.verify()
    decoded = Image.open(io.BytesIO(raw))
    decoded.load()
    return decoded


def test_render_comment_image_produces_valid_png():
    from nonebot_plugin_larkcave.utils.comment.render import CANVAS_WIDTH, render_comment_image

    raw = render_comment_image(
        "回声洞评论 —— (1)",
        "由 Moonlark 生成",
        [_view(), _view(nickname="Moon", text="第二条评论"), _view(text="第三条")],
    )
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    image = _decode(raw)
    assert image.size == (CANVAS_WIDTH, image.size[1])
    assert image.size[1] > 60


def test_render_comment_image_wraps_long_text():
    from nonebot_plugin_larkcave.utils.comment.render import render_comment_image

    short = _decode(render_comment_image("t", "f", [_view(text="短评论")])).size[1]
    long = _decode(render_comment_image("t", "f", [_view(text="很长" * 200)])).size[1]
    assert long > short


def test_render_comment_image_wider_canvas_for_long_text():
    from nonebot_plugin_larkcave.utils.comment.render import CANVAS_WIDTH, render_comment_image

    # 单行超长英文也应被截断在气泡最大宽度内，不超出画布
    image = _decode(render_comment_image("t", "f", [_view(text="a" * 300)]))
    assert image.size[0] == CANVAS_WIDTH


def test_render_comment_image_multiline_text():
    from nonebot_plugin_larkcave.utils.comment.render import render_comment_image

    single = _decode(render_comment_image("t", "f", [_view(text="a")])).size[1]
    multi = _decode(render_comment_image("t", "f", [_view(text="a\nb\nc")])).size[1]
    assert multi > single


def test_render_comment_image_deterministic():
    from nonebot_plugin_larkcave.utils.comment.render import render_comment_image

    comments = [_view(nickname="测试"), _view(nickname="Moon", text="第二条")]
    assert render_comment_image("t", "f", comments) == render_comment_image("t", "f", comments)


def test_render_comment_image_empty_nickname_fallback():
    from nonebot_plugin_larkcave.utils.comment.render import render_comment_image

    raw = render_comment_image("t", "f", [_view(nickname="")])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
