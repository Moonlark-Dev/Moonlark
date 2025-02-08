from nonebot import logger, require
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_github",
    description="",
    usage="",
)


require("nonebot_plugin_render")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from nonebot_plugin_alconna import Alconna, Args, on_alconna, UniMessage
from nonebot import on_keyword
from nonebot.adapters import Event
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_render import render_template
from nonebot_plugin_larkutils import get_user_id
from . import data_source


github_command = on_alconna(Alconna("github", Args["url", str]))
github_keyword = on_keyword({"/"}, block=False, priority=5)
lang = LangHelper()


async def github_handler(matcher, url: str, user_id: str, reply_unknown_url: bool) -> None:
    try:
        await _github_handler(matcher, url, user_id, reply_unknown_url)
    except FinishedException:
        pass
    except Exception:
        await matcher.finish(await lang.text("error", user_id))


async def _github_handler(matcher, url: str, user_id: str, reply_unknown_url: bool) -> None:
    data = await data_source.parse_github(url)
    logger.debug(str(data))
    if data is None or data["type"] == "none":
        if reply_unknown_url:
            await lang.finish("unknown_url", user_id)
        return
    await matcher.finish(
        await UniMessage()
        .image(
            raw=await render_template(
                "github.html.jinja",
                await lang.text("title", user_id),
                user_id,
                {
                    "data": data,
                    "text": {
                        "repo": {
                            "star": await lang.text("repo.star", user_id),
                            "forks": await lang.text("repo.forks", user_id),
                            "issues": await lang.text("repo.issues", user_id),
                            "language": await lang.text("repo.language", user_id),
                        },
                        "issues": {
                            "open": await lang.text("issues.open", user_id),
                            "closed": await lang.text("issues.closed", user_id),
                        },
                        "discussion": {
                            "at": await lang.text("discussion.at", user_id),
                        },
                        "user": {
                            "followers": await lang.text("user.followers", user_id),
                            "following": await lang.text("user.following", user_id),
                            "public_repos": await lang.text("user.public_repos", user_id),
                            "location": await lang.text("user.location", user_id),
                        },
                        "pull": {
                            "wants_to_merge": await lang.text("pull.want", user_id),
                            "into": await lang.text("pull.into", user_id),
                            "merged": await lang.text("pull.merged", user_id),
                        },
                    },
                },
            )
        )
        .export()
    )


@github_command.handle()
async def _(url: str, user_id: str = get_user_id()):
    await github_handler(github_command, url, user_id, True)


@github_keyword.handle()
async def _(event: Event, user_id: str = get_user_id()):
    url = event.get_plaintext()
    await github_handler(github_keyword, url, user_id, False)
