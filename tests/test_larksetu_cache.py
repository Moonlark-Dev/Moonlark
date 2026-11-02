"""nonebot_plugin_larksetu 缓存与 #setu-g 的回归测试。

覆盖：签到卡片头图使用的图片在 TTL 内可按 ID 取回、过期后可被清理、
随机抽取的图片不保留原图、旧版缓存索引兼容、以及 #setu-g 不计入 setu 排行。
"""

import json
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException


class _FakeLang:
    """记录 lang.finish 的 key，并像真实实现一样用 FinishedException 截断处理器"""

    def __init__(self) -> None:
        self.finished: list[str] = []

    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return key

    async def finish(self, key: str, _user_id: str, *args: object) -> None:
        self.finished.append(key)
        raise FinishedException


class _Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


def _make_data(pid: int = 1, p: int = 0, width: int = 1920, height: int = 1080, ext: str = "jpg"):
    from nonebot_plugin_larksetu.models import ImageData

    return ImageData(
        pid=pid,
        p=p,
        uid=1,
        title=f"title-{pid}",
        author=f"author-{pid}",
        r18=False,
        width=width,
        height=height,
        tags=[],
        ext=ext,
        aiType=0,
        uploadDate=0,
        urls={"original": "https://example.com/image.jpg"},
    )


@pytest.fixture
def setu_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """把缓存目录指向临时目录，并冻结时间、禁用后台补缓存与网络下载"""
    import nonebot_plugin_larksetu.cache as cache
    from nonebot_plugin_larksetu.config import config

    clock = _Clock()
    monkeypatch.setattr(cache, "cache_dir", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(cache, "time", clock)
    # 测试中不允许真的下载图片，需要时由用例自己覆盖
    monkeypatch.setattr(cache, "get_new_image", AsyncMock(side_effect=AssertionError("不应下载新图片")))
    monkeypatch.setattr(cache, "request_refill", lambda: None)
    monkeypatch.setattr(config, "setu_cache_count", 10)
    monkeypatch.setattr(config, "setu_cache_ttl", 60)
    return cache, clock


@pytest.mark.asyncio
async def test_landscape_image_is_retained_for_viewing(setu_env) -> None:
    """签到卡片取走的横版图在 TTL 内仍可按 ID 取回原图与元数据"""
    cache, _ = setu_env
    data = _make_data(pid=42, width=1920, height=1080)
    await cache._store_entry(data, b"original")
    image_id = cache.get_image_id(data)

    image = await cache.get_landscape_image()

    assert image is not None
    assert image["image"] == b"original"
    assert image["data"].pid == 42
    # 已被取出：可用池清空，但图片本身仍保留
    assert await cache._get_pool_size() == 0
    cached = await cache.get_cached_image(image_id)
    assert cached is not None
    assert cached["image"] == b"original"
    assert cached["data"].title == "title-42"


@pytest.mark.asyncio
async def test_used_image_is_not_drawn_by_random(monkeypatch: pytest.MonkeyPatch, setu_env) -> None:
    """已发放给签到卡片的图片不会再被 #setu 随机抽到"""
    cache, _ = setu_env
    portrait = _make_data(pid=7, width=1080, height=1920)
    monkeypatch.setattr(cache, "get_new_image", AsyncMock(return_value={"data": portrait, "image": b"portrait"}))
    used = _make_data(pid=1, width=1920, height=1080)
    await cache._store_entry(used, b"landscape")
    image_id = cache.get_image_id(used)

    assert await cache.get_landscape_image() is not None
    # 池中没有横版图时补一张新图：不是横版就放回缓存并返回 None
    assert await cache.get_landscape_image() is None
    # 随机抽取只会抽到新补的图片
    drawn = await cache.get_image()
    assert drawn["image"] == b"portrait"
    cached = await cache.get_cached_image(image_id)
    assert cached is not None and cached["image"] == b"landscape"


@pytest.mark.asyncio
async def test_used_image_expires_after_ttl(setu_env) -> None:
    """已发放的图片超过 TTL 后按 ID 取不到，缓存文件也会被清理"""
    cache, clock = setu_env
    data = _make_data(pid=3)
    await cache._store_entry(data, b"img")
    await cache.get_landscape_image()

    clock.now += 61

    assert await cache.get_cached_image(cache.get_image_id(data)) is None
    assert not cache._get_image_file(data).exists()


@pytest.mark.asyncio
async def test_random_image_is_not_retained(setu_env) -> None:
    """#setu 随机抽出的图片不保留原图，避免缓存无限增长"""
    cache, _ = setu_env
    data = _make_data(pid=9)
    await cache._store_entry(data, b"img")

    image = await cache.get_image()

    assert image["image"] == b"img"
    assert await cache.get_cached_image(cache.get_image_id(data)) is None
    assert not cache._get_image_file(data).exists()


@pytest.mark.asyncio
async def test_legacy_cache_index_is_migrated(setu_env) -> None:
    """旧版本直接保存 ImageData 列表的 cache.json 仍可读取"""
    cache, _ = setu_env
    data = _make_data(pid=11)
    cache.CACHE_FILE.write_text(json.dumps([data.model_dump()]), encoding="utf-8")
    await cache._write_image_file(data, b"legacy")

    index = await cache._load_index()

    assert len(index.entries) == 1
    assert not index.entries[0].is_used
    cached = await cache.get_cached_image(cache.get_image_id(data))
    assert cached is not None and cached["image"] == b"legacy"


@pytest.mark.asyncio
async def test_pool_is_trimmed_to_cache_count(monkeypatch: pytest.MonkeyPatch, setu_env) -> None:
    """可用池超过 setu_cache_count 时淘汰最旧的图片"""
    cache, _ = setu_env
    from nonebot_plugin_larksetu.config import config

    monkeypatch.setattr(config, "setu_cache_count", 2)
    first = _make_data(pid=1)
    await cache._store_entry(first, b"1")
    await cache._store_entry(_make_data(pid=2), b"2")
    await cache._store_entry(_make_data(pid=3), b"3")

    assert await cache._get_pool_size() == 2
    assert not cache._get_image_file(first).exists()
    assert await cache.get_cached_image(cache.get_image_id(first)) is None


@pytest.mark.asyncio
async def test_duplicate_image_is_not_added_twice(setu_env) -> None:
    """同一张图片被重复补进缓存时不会产生重复记录"""
    cache, _ = setu_env
    data = _make_data(pid=5)
    await cache._store_entry(data, b"a")
    await cache._store_entry(data, b"a")

    assert await cache._get_pool_size() == 1


@pytest.fixture
def setu_g_env(monkeypatch: pytest.MonkeyPatch):
    import nonebot_plugin_larksetu.__main__ as main_module
    from nonebot_plugin_alconna import UniMessage

    fake_lang = _FakeLang()
    monkeypatch.setattr(main_module, "lang", fake_lang)
    counter_add = AsyncMock()
    monkeypatch.setattr(main_module.counter, "add", counter_add)
    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    monkeypatch.setattr(UniMessage, "send", fake_send)
    return main_module, fake_lang, counter_add, sent


@pytest.mark.asyncio
async def test_setu_g_sends_cached_image_without_ranking(monkeypatch: pytest.MonkeyPatch, setu_g_env) -> None:
    """#setu-g 从缓存发送原图与元数据，且不计入 setu 排行"""
    from nonebot_plugin_alconna import Image, Text

    main_module, fake_lang, counter_add, sent = setu_g_env
    data = _make_data(pid=42)
    monkeypatch.setattr(
        main_module,
        "get_cached_image",
        AsyncMock(return_value={"data": data, "image": b"original"}),
    )

    with pytest.raises(FinishedException):
        await main_module._setu_get_handler("42_0", user_id="10")

    counter_add.assert_not_awaited()
    assert fake_lang.finished == []
    image = next(segment for segment in sent[0] if isinstance(segment, Image))
    assert image.raw == b"original"
    text = next(segment for segment in sent[0] if isinstance(segment, Text))
    assert text.text == "setu.info"


@pytest.mark.asyncio
async def test_setu_g_finishes_when_image_expired(monkeypatch: pytest.MonkeyPatch, setu_g_env) -> None:
    """按 ID 取不到（已过期或不存在）时提示原图不存在"""
    main_module, fake_lang, _, sent = setu_g_env
    monkeypatch.setattr(main_module, "get_cached_image", AsyncMock(return_value=None))

    with pytest.raises(FinishedException):
        await main_module._setu_get_handler("123_0", user_id="10")

    assert fake_lang.finished == ["setu.expired"]
    assert sent == []
