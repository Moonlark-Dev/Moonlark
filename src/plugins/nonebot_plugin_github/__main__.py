from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
import re
import httpx
from nonebot.plugin.on import on_keyword
from ..nonebot_plugin_render.render import render_template
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils.user import get_user_id

lang = LangHelper()

alc = Alconna("github", Args["url", str])
github_command = on_alconna(alc)
github_keyword = on_keyword({"/"})


@github_command.handle()
async def _(url: str):
    await github_handler(github_command, url)


@github_keyword.handle()
async def _(url: str):
    await github_handler(github_keyword, url)


# 直接把消息内容调用 parse_github
async def github_handler(matcher, url):
    pass


def rreplace(s, old, new, count=1):
    return new.join(s.rsplit(old, count))


def extract_github_path(url):
    url = rreplace(url, "/pull/", "/pulls/")
    pattern = r'^(?:https?://)?(?:www\.)?github\.com/([^?#]+)'
    match = re.search(pattern, url, re.IGNORECASE)
    if match:
        return match.group(1)
    return url


def extract_github_section(url: str):
    match len(url.split("/")):
        case 0:
            return "none"
        case 1:
            return "user"
        case 2:
            return "repo"
    pattern = r'^([^/]+)/([^/]+)/([^/]+)/?.*$'
    match = re.match(pattern, url.strip())
    if match:
        return match.groups()[2]


async def parse_github(url):
    api_url = "https://api.github.com/repos/" + (uri := extract_github_path(url))
    if (section := extract_github_section(uri)) == "user":
        api_url = "https://api.github.com/users/" + uri
    if "://" in uri or section == "none":
        return {"type": "none"}
    async with httpx.AsyncClient() as client:
        response = (await client.get(api_url)).json()
    if response.get("status") == "404":
        return {"type": "none"}
    match section:
        case "repo":
            return {
                "type": "repo",
                "repo": response["full_name"],
                "description": response["description"],
                "stars": response["stargazers_count"],
                "forks": response["forks_count"],
                "issues": response["open_issues_count"],
                "language": response["language"],
                "avatar": response["owner"]["avatar_url"]
            }
        case "issues":
            return {
                "type": "issue",
                "repo": response["repository_url"].replace("https://api.github.com/repos/", ""),
                "user": response["user"]["login"],
                "title": response["title"],
                "number": response["number"],
                "labels": response["labels"],
                "state": response["state"],
                "comments": response["comments"],
                "updated_at": response["updated_at"],
                "avatar": response["user"]["avatar_url"]
            }
        case "discussions":
            return {
                "type": "discussion",
                "repo": response["repository_url"].replace("https://api.github.com/repos/", ""),
                "user": response["user"]["login"],
                "title": response["title"],
                "number": response["number"],
                "labels": response["labels"],
                "state": response["state"],
                "comments": response["comments"],
                "updated_at": response["updated_at"],
                "category": response["category"]["name"],
                "avatar": response["user"]["avatar_url"]
            }
        case "pulls":
            return {
                "type": "pull",
                "repo": response["base"]["repo"]["full_name"],
                "user": response["user"]["login"],
                "title": response["title"],
                "number": response["number"],
                "labels": response["labels"],
                "state": response["state"],
                "comments": response["comments"],
                "updated_at": response["updated_at"],
                "avatar": response["user"]["avatar_url"],
                "from": response["head"]["label"],
                "to": response["base"]["label"]
            }
        case "user":
            return {
                "type": response["type"].lower(), # 可能是 user 或 organization
                "login": response["login"],
                "name": response["name"],
                "bio": response["bio"],
                "followers": response["followers"],
                "following": response["following"],
                "public_repos": response["public_repos"],
                "avatar": response["avatar_url"],
                "location": response["location"],
                "email": response["email"],
            }
