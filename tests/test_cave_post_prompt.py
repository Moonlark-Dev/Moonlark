from typing import ClassVar

import pytest


class _FakeSubcommand:
    def __init__(self, args: dict):
        self.args = args


class _FakeResult:
    def __init__(self, add_args: dict):
        self.subcommands = {"add": _FakeSubcommand(add_args)}


class _FakeCaveWaiter:
    """替换 nonebot_plugin_larkcave.commands.post.Waiter 的测试替身"""

    created: ClassVar[list] = []
    responses: ClassVar[list] = []

    def __init__(self, prompt_text, user_id, **kwargs) -> None:
        self.prompt_text = prompt_text
        self.user_id = user_id
        self.kwargs = kwargs
        type(self).created.append(self)

    async def wait(self, timeout: int = 210, auto_finish: bool = True) -> None:
        self.timeout = timeout
        self.auto_finish = auto_finish
        response = type(self).responses.pop(0)
        if isinstance(response, Exception):
            raise response
        self._message = response

    def get(self, parser=lambda message: message):
        return parser(self._message)


@pytest.fixture
def cave_post_env(monkeypatch):
    """隔离 post 模块的外部依赖：Waiter、post_cave 与 lang"""
    from nonebot.exception import FinishedException
    import nonebot_plugin_larkcave.commands.post as post_mod

    posted: list[tuple[list, str]] = []
    finished: list[tuple[str, str]] = []

    async def fake_post_cave(content, user_id, event, bot, state, session, group_id=None):
        posted.append((content, user_id))

    async def fake_lang_text(key: str, user_id, *args, **kwargs) -> str:
        return f"text::{key}"

    async def fake_lang_finish(key: str, user_id, *args, **kwargs):
        finished.append((key, str(user_id)))
        raise FinishedException

    monkeypatch.setattr(post_mod, "post_cave", fake_post_cave)
    monkeypatch.setattr(post_mod.lang, "text", fake_lang_text)
    monkeypatch.setattr(post_mod.lang, "finish", fake_lang_finish)
    monkeypatch.setattr(post_mod, "Waiter", _FakeCaveWaiter)

    _FakeCaveWaiter.created.clear()
    _FakeCaveWaiter.responses.clear()
    return {"posted": posted, "finished": finished}


@pytest.mark.asyncio
async def test_cave_a_rich_reply_posts_image_and_text(cave_post_env):
    """/cave-a 未携带内容时，补发的图片+文本富文本内容应完整投稿"""
    from nonebot_plugin_alconna import Image, Text, UniMessage
    from nonebot_plugin_larkcave.commands.post import handle_add

    _FakeCaveWaiter.responses.append(UniMessage([Text("  "), Image("https://example.com/a.png"), Text("看图")]))

    result = _FakeResult({})  # add 子命令存在但没有 content 参数
    await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert len(_FakeCaveWaiter.created) == 1
    waiter = _FakeCaveWaiter.created[0]
    assert waiter.user_id == "user-1"
    assert waiter.prompt_text.extract_plain_text() == "text::add.prompt"
    assert waiter.timeout == 60
    assert waiter.auto_finish is False

    assert len(cave_post_env["posted"]) == 1
    content, user_id = cave_post_env["posted"][0]
    assert user_id == "user-1"
    # 空白文本段被过滤，图片与有效文本完整保留
    assert len([seg for seg in content if isinstance(seg, Image)]) == 1
    assert [seg.text for seg in content if isinstance(seg, Text)] == ["看图"]


@pytest.mark.asyncio
async def test_cave_a_plain_reply_posts_text(cave_post_env):
    """/cave-a 补发纯文本时按原逻辑投稿"""
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_larkcave.commands.post import handle_add

    _FakeCaveWaiter.responses.append(UniMessage([Text("用户回复的投稿内容")]))

    result = _FakeResult({})
    await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert cave_post_env["finished"] == []
    assert len(cave_post_env["posted"]) == 1
    content, user_id = cave_post_env["posted"][0]
    assert user_id == "user-1"
    assert [seg.text for seg in content if isinstance(seg, Text)] == ["用户回复的投稿内容"]


@pytest.mark.asyncio
async def test_cave_a_whitespace_reply_falls_back_to_empty(cave_post_env):
    """/cave-a 未携带内容且用户回复空白内容时，按无效内容结束投稿"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_larkcave.commands.post import handle_add

    _FakeCaveWaiter.responses.append(UniMessage([Text("   ")]))
    result = _FakeResult({})
    with pytest.raises(FinishedException):
        await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert cave_post_env["posted"] == []
    assert cave_post_env["finished"] == [("add.empty", "user-1")]


@pytest.mark.asyncio
async def test_cave_a_q_reply_cancels(cave_post_env):
    """/cave-a 补发 q 时取消投稿"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_larkcave.commands.post import handle_add

    _FakeCaveWaiter.responses.append(UniMessage([Text("Q")]))
    result = _FakeResult({})
    with pytest.raises(FinishedException):
        await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert cave_post_env["posted"] == []
    assert cave_post_env["finished"] == [("prompt.cancelled", "user-1")]


@pytest.mark.asyncio
async def test_cave_a_timeout_finishes(cave_post_env):
    """/cave-a 等待补发内容超时时结束会话"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_larkcave.commands.post import handle_add

    _FakeCaveWaiter.responses.append(TimeoutError())
    result = _FakeResult({})
    with pytest.raises(FinishedException):
        await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert cave_post_env["posted"] == []
    assert cave_post_env["finished"] == [("add.timeout", "user-1")]


@pytest.mark.asyncio
async def test_cave_a_with_content_posts_directly(cave_post_env):
    """/cave-a 携带内容时直接投稿，不触发富文本询问"""
    from nonebot_plugin_alconna import Text
    from nonebot_plugin_larkcave.commands.post import handle_add

    result = _FakeResult({"content": (Text("直接投稿内容"),)})
    await handle_add(None, None, None, None, result, user_id="user-1", group_id="group-1")

    assert _FakeCaveWaiter.created == []
    assert len(cave_post_env["posted"]) == 1
    content, user_id = cave_post_env["posted"][0]
    assert user_id == "user-1"
    assert [seg.text for seg in content if isinstance(seg, Text)] == ["直接投稿内容"]


@pytest.mark.asyncio
async def test_cave_a_empty_now_matches_command():
    """/cave-a 不带内容时命令应能匹配（不再因缺少参数而解析失败）"""
    from nonebot_plugin_larkcave.__main__ import cave

    cmd = cave.command()
    assert cmd is not None
    res = cmd.parse("/cave-a")
    assert res.matched is True
    assert list(res.subcommands.keys()) == ["add"]
