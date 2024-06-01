from nonebot_plugin_htmlrender import template_to_pic
from pathlib import Path
from .models import CommentData
from ...lang import lang
from ....nonebot_plugin_larkuser import get_user

async def generate(comments: list[CommentData], cave_id: int, user_id: str) -> bytes:
    return await template_to_pic(
        Path(__file__).parent.joinpath("templates").as_posix(),
        "index.html.jinja",
        {
            "title": await lang.text("comment.title", user_id, cave_id),
            "footer": await lang.text("comment.footer", user_id),
            "comments": [
                {
                    "author": (await get_user(comment.author)).nickname,
                    "time": comment.time.strftime("%Y-%m-%d %H:%M:%S"),
                    "id": await lang.text("comment.id", user_id, comment.id),
                    "text": comment.content.replace("<", "&lt;").replace(">", "&gt;")
                } for comment in comments
            ]
        }
    )