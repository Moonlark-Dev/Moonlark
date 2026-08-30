"""ranking find_user 回归测试：display 键缺失时不应输出 None

修复场景：GET /api/rankings/setu 报
`ResponseValidationError: ('response', 'me', 'display') -> Input should be a valid string`，
因为排行数据不带 display 键时，find_user 仍会输出 {"display": None}，
而 UserDataWithIndex.display 是 NotRequired[str]，None 值无法通过 FastAPI 响应校验。

注意：插件导入必须发生在测试函数/fixture 内部（collection 阶段 nonebot 插件尚未加载）。
"""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from nonebot_plugin_ranking.types import RankingData


@pytest.fixture
def _patched_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离 find_user 的 get_user / LangHelper 依赖，避免访问真实数据库"""
    import nonebot_plugin_ranking.generator as generator

    fake_user = MagicMock()
    fake_user.get_nickname.return_value = "测试昵称"
    monkeypatch.setattr(generator, "get_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(generator.lang, "text", AsyncMock(return_value="rank.info"))


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patched_deps")
async def test_find_user_omits_display_when_missing() -> None:
    """排行数据无 display 键时，返回值不应包含 display 键"""
    from nonebot_plugin_ranking.generator import find_user

    data: list[RankingData] = [{"user_id": "u1", "data": 10, "info": None}]
    result = await find_user(data, "u1")
    assert result is not None
    assert "display" not in result


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patched_deps")
async def test_find_user_keeps_display_when_present() -> None:
    """排行数据带 display 键时，返回值应原样保留该键"""
    from nonebot_plugin_ranking.generator import find_user

    data: list[RankingData] = [{"user_id": "u1", "data": 10, "info": None, "display": "07:00:00"}]
    result = await find_user(data, "u1")
    assert result is not None
    assert result["display"] == "07:00:00"
