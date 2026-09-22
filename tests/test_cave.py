import pytest
from unittest.mock import patch
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import NoResultFound


@pytest.fixture
async def eng():
    from nonebot_plugin_larkcave.models import CaveData

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(CaveData.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(CaveData.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(eng):
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture
async def seed_caves(session):
    from nonebot_plugin_larkcave.models import CaveData

    caves = [
        CaveData(id=1, author="a", content="普通内容没有关键词", time=datetime(2026, 1, 1), public=True),
        CaveData(id=2, author="b", content="星期四快乐 50 KFC", time=datetime(2026, 1, 1), public=True),
        CaveData(id=3, author="c", content="今天星期四", time=datetime(2026, 1, 1), public=True),
        CaveData(id=4, author="d", content="[[Img:1674571532.0250726]]", time=datetime(2026, 1, 1), public=True),
        CaveData(id=5, author="e", content="KFC疯狂星期四", time=datetime(2026, 1, 1), public=True),
        CaveData(id=6, author="f", content="数字50在文本中", time=datetime(2026, 1, 1), public=True),
        CaveData(id=7, author="g", content="kfc 小写", time=datetime(2026, 1, 1), public=True),
        CaveData(id=8, author="h", content="private only", time=datetime(2026, 1, 1), public=False),
    ]
    session.add_all(caves)
    await session.commit()
    return caves


# ========== _random_keyword_cave tests ==========


@pytest.mark.asyncio
async def test_random_cave_no_filter_returns_any(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave

    result = await _random_keyword_cave(session)
    assert result is not None
    assert result.public is True


@pytest.mark.asyncio
async def test_random_cave_no_filter_ignores_private(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave

    for _ in range(5):
        result = await _random_keyword_cave(session)
        assert result is not None
        assert result.public is True


@pytest.mark.asyncio
async def test_random_cave_require_keywords_returns_matching(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave, THURSDAY_KEYWORDS

    for _ in range(10):
        result = await _random_keyword_cave(session, require_keywords=True)
        assert result is not None
        assert any(kw.lower() in result.content.lower() for kw in THURSDAY_KEYWORDS)
        assert "[[img" not in result.content.lower()


@pytest.mark.asyncio
async def test_random_cave_require_keywords_excludes_image(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave

    for _ in range(10):
        result = await _random_keyword_cave(session, require_keywords=True)
        if result is not None:
            assert "[[img" not in result.content.lower()


@pytest.mark.asyncio
async def test_random_cave_exclude_keywords_returns_non_matching(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave, THURSDAY_KEYWORDS

    for _ in range(10):
        result = await _random_keyword_cave(session, require_keywords=False)
        assert result is not None
        assert not any(kw.lower() in result.content.lower() for kw in THURSDAY_KEYWORDS)


@pytest.mark.asyncio
async def test_random_cave_keyword_empty_returns_none(session):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave

    result = await _random_keyword_cave(session, require_keywords=True)
    assert result is None


@pytest.mark.asyncio
async def test_random_cave_nonkeyword_empty_returns_none(session):
    from nonebot_plugin_larkcave.models import CaveData
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave

    caves = [
        CaveData(id=10, author="a", content="星期四快乐 50 KFC", time=datetime(2026, 1, 1), public=True),
        CaveData(id=11, author="b", content="今天星期四", time=datetime(2026, 1, 1), public=True),
    ]
    session.add_all(caves)
    await session.commit()
    result = await _random_keyword_cave(session, require_keywords=False)
    assert result is None


@pytest.mark.asyncio
async def test_random_cave_empty_db_returns_none(session):
    from nonebot_plugin_larkcave.utils.cave import _random_keyword_cave

    result = await _random_keyword_cave(session)
    assert result is None


# ========== get_cave: non-Thursday tests ==========


@pytest.mark.asyncio
async def test_get_cave_non_thursday_no_keywords(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import get_cave

    with patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = datetime(2026, 7, 29)
        mock_dt.datetime.now.weekday.return_value = 2
        cave = await get_cave(session)
        assert cave is not None
        assert cave.public is True


@pytest.mark.asyncio
async def test_get_cave_non_thursday_empty_db(session):
    from nonebot_plugin_larkcave.utils.cave import get_cave

    with patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = datetime(2026, 7, 29)
        mock_dt.datetime.now.weekday.return_value = 2
        with pytest.raises(IndexError):
            await get_cave(session)


# ========== get_cave: Thursday tests ==========


@pytest.mark.asyncio
async def test_get_cave_thursday_keyword_path(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import get_cave, THURSDAY_KEYWORDS

    with (
        patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt,
        patch("nonebot_plugin_larkcave.utils.cave.random.random", return_value=0.3),
    ):
        mock_dt.datetime.now.return_value = datetime(2026, 7, 30)
        mock_dt.datetime.now.weekday.return_value = 3
        cave = await get_cave(session)
        assert cave is not None
        assert any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)
        assert "[[img" not in cave.content.lower()


@pytest.mark.asyncio
async def test_get_cave_thursday_nonkeyword_path(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import get_cave, THURSDAY_KEYWORDS

    with (
        patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt,
        patch("nonebot_plugin_larkcave.utils.cave.random.random", return_value=0.7),
    ):
        mock_dt.datetime.now.return_value = datetime(2026, 7, 30)
        mock_dt.datetime.now.weekday.return_value = 3
        cave = await get_cave(session)
        assert cave is not None
        assert not any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)


@pytest.mark.asyncio
async def test_get_cave_thursday_keyword_fallback_to_nonkeyword(session):
    from nonebot_plugin_larkcave.models import CaveData
    from nonebot_plugin_larkcave.utils.cave import get_cave, THURSDAY_KEYWORDS

    caves = [
        CaveData(id=20, author="a", content="普通内容", time=datetime(2026, 1, 1), public=True),
    ]
    session.add_all(caves)
    await session.commit()
    with (
        patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt,
        patch("nonebot_plugin_larkcave.utils.cave.random.random", return_value=0.3),
    ):
        mock_dt.datetime.now.return_value = datetime(2026, 7, 30)
        mock_dt.datetime.now.weekday.return_value = 3
        cave = await get_cave(session)
        assert cave is not None
        assert not any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)


@pytest.mark.asyncio
async def test_get_cave_thursday_nonkeyword_fallback_to_keyword(session):
    from nonebot_plugin_larkcave.models import CaveData
    from nonebot_plugin_larkcave.utils.cave import get_cave, THURSDAY_KEYWORDS

    caves = [
        CaveData(id=30, author="a", content="星期四 50 KFC", time=datetime(2026, 1, 1), public=True),
    ]
    session.add_all(caves)
    await session.commit()
    with (
        patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt,
        patch("nonebot_plugin_larkcave.utils.cave.random.random", return_value=0.7),
    ):
        mock_dt.datetime.now.return_value = datetime(2026, 7, 30)
        mock_dt.datetime.now.weekday.return_value = 3
        cave = await get_cave(session)
        assert cave is not None
        assert any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)


@pytest.mark.asyncio
async def test_get_cave_thursday_no_caves(session):
    from nonebot_plugin_larkcave.utils.cave import get_cave

    with (
        patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt,
        patch("nonebot_plugin_larkcave.utils.cave.random.random", return_value=0.3),
    ):
        mock_dt.datetime.now.return_value = datetime(2026, 7, 30)
        mock_dt.datetime.now.weekday.return_value = 3
        with pytest.raises(NoResultFound):
            await get_cave(session)


# ========== Edge cases ==========


@pytest.mark.asyncio
async def test_get_cave_thursday_40_60_distribution(session, seed_caves):
    from nonebot_plugin_larkcave.utils.cave import get_cave, THURSDAY_KEYWORDS

    for rand_val, expect_keyword in [(0.0, True), (0.39, True), (0.4, False), (0.99, False)]:
        with (
            patch("nonebot_plugin_larkcave.utils.cave.datetime") as mock_dt,
            patch("nonebot_plugin_larkcave.utils.cave.random.random", return_value=rand_val),
        ):
            mock_dt.datetime.now.return_value = datetime(2026, 7, 30)
            mock_dt.datetime.now.weekday.return_value = 3
            cave = await get_cave(session)
            assert cave is not None
            if expect_keyword:
                assert any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)
            else:
                assert not any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)
