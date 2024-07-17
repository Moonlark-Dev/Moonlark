from ....nonebot_plugin_render.render import render_template
from .models import CommentData
from ...lang import lang
from ....nonebot_plugin_larkuser import get_user


async def generate(comments: list[CommentData], cave_id: int, user_id: str) -> bytes:
    return await render_template(
        "cave_commant.html.jinja",
        await lang.text("comment.title", user_id, cave_id),
        user_id,
        {
            "comments": [
                {
                    "author": (await get_user(comment.author)).get_nickname(),
                    "time": comment.time.strftime("%Y-%m-%d %H:%M:%S"),
                    "id": await lang.text("comment.id", user_id, comment.id),
                    "text": comment.content.replace("<", "&lt;").replace(">", "&gt;"),
                }
                for comment in comments
            ]
        },
    )
