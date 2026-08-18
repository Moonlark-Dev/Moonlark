import pytest


class _FakeSubcommand:
    def __init__(self, args: dict):
        self.args = args


class _FakeResult:
    def __init__(self, add_args: dict):
        self.subcommands = {"add": _FakeSubcommand(add_args)}


@pytest.mark.asyncio
async def test_cave_a_without_content_prompts_then_posts(monkeypatch):
    """/cave-a 未携带内容时，先通过 LarkUser prompt 询问投稿内容，再以回复内容投稿"""
    from nonebot_plugin_alconna import Text
    from nonebot_plugin_larkcave.commands.post import handle_add

    prompt_message = "投稿内容为空！请直接发送您要投稿到回声洞的内容。\n发送 q 可取消本次投稿。"
    prompted: list[tuple[str, str, dict]] = []
    posted: list[tuple[list, str]] = []

    async def fake_prompt(message, user_id, **kwargs):
        prompted.append((message, user_id, kwargs))
        return "用户回复的投稿内容"

    async def fake_post_cave(content, user_id, event, bot, state, session, group_id=None):
        posted.append((content, user_id))

    async def fake_lang_text(key: str, user_id, *args, **kwargs) -> str:
        return prompt_message

    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.prompt", fake_prompt)
    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.post_cave", fake_post_cave)
    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.lang.text", fake_lang_text)

    result = _FakeResult({})  # add 子命令存在但没有 content 参数
    await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert prompted == [
        (prompt_message, "user-1", {"timeout": 60}),
    ]
    assert len(posted) == 1
    content, user_id = posted[0]
    assert user_id == "user-1"
    assert [seg.text for seg in content if isinstance(seg, Text)] == ["用户回复的投稿内容"]


@pytest.mark.asyncio
async def test_cave_a_with_content_posts_directly(monkeypatch):
    """/cave-a 携带内容时直接投稿，不触发询问"""
    from nonebot_plugin_alconna import Text
    from nonebot_plugin_larkcave.commands.post import handle_add

    prompted = []
    posted: list[tuple[list, str]] = []

    async def fake_prompt(message, user_id, **kwargs):
        prompted.append(message)
        return ""

    async def fake_post_cave(content, user_id, event, bot, state, session, group_id=None):
        posted.append((content, user_id))

    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.prompt", fake_prompt)
    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.post_cave", fake_post_cave)

    result = _FakeResult({"content": (Text("直接投稿内容"),)})
    await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert prompted == []
    assert len(posted) == 1
    content, user_id = posted[0]
    assert user_id == "user-1"
    assert [seg.text for seg in content if isinstance(seg, Text)] == ["直接投稿内容"]


@pytest.mark.asyncio
async def test_cave_a_empty_reply_falls_back_to_invalid(monkeypatch):
    """/cave-a 未携带内容且用户回复空内容时，按无效内容结束投稿"""
    from nonebot_plugin_larkcave.commands.post import handle_add

    finished = []

    async def fake_prompt(message, user_id, **kwargs):
        return "   "

    async def fake_lang_finish(key: str, user_id, *args, **kwargs):
        finished.append((key, user_id))

    async def fake_post_cave(content, user_id, event, bot, state, session, group_id=None):
        raise AssertionError("不应投稿空内容")

    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.prompt", fake_prompt)
    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.post_cave", fake_post_cave)
    monkeypatch.setattr("nonebot_plugin_larkcave.commands.post.lang.finish", fake_lang_finish)

    result = _FakeResult({})
    await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert finished == [("add.empty", "user-1")]


@pytest.mark.asyncio
async def test_cave_a_empty_now_matches_command():
    """/cave-a 不带内容时命令应能匹配（不再因缺少参数而解析失败）"""
    from nonebot_plugin_larkcave.__main__ import cave

    cmd = cave.command()
    assert cmd is not None
    res = cmd.parse("/cave-a")
    assert res.matched is True
    assert list(res.subcommands.keys()) == ["add"]
