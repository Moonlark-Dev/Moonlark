"""larklang 语言键缓存改为内存后的回归测试。

原先语言键被写入数据库表 nonebot_plugin_larklang_languagekeycache，
读取时每次都要查询数据库；现在改为在启动时解析进内存（LanguageData.keys）。
"""

from pathlib import Path

import pytest


def test_language_key_cache_model_removed() -> None:
    """数据库缓存表对应的 ORM 模型应当已被移除"""
    from nonebot_plugin_larklang import models

    assert not hasattr(models, "LanguageKeyCache")


def test_language_data_holds_keys(tmp_path: Path) -> None:
    """LanguageData 增加内存键表字段，且每个实例互不共享"""
    from nonebot_plugin_larklang.models import LanguageData

    first = LanguageData(path=tmp_path)
    second = LanguageData(path=tmp_path)
    assert first.keys == {}
    first.keys["plugin"] = {}
    assert second.keys == {}


@pytest.mark.asyncio
async def test_language_keys_loaded_from_memory() -> None:
    """载入后直接查内存：不再需要数据库会话"""
    from nonebot_plugin_larklang.__main__ import get_languages, get_text, load_languages

    await load_languages()
    languages = get_languages()

    assert "zh_hans" in languages
    assert "buff" in languages["zh_hans"].keys
    assert "list.title" in languages["zh_hans"].keys["buff"]

    assert get_text("zh_hans", "buff", "duration.second", 3) == "3 秒"
    assert get_text("zh_hans", "broadcast", "bc.group_only") == "此命令只能在群聊中使用"

    # 缺失的键仍然返回占位文本
    assert get_text("zh_hans", "buff", "not.exist").startswith("[缺失: ")

    # 指定语言缺失时回退到其它语言
    assert get_text("zh_hans", "vote", "status.open") == "进行中"


@pytest.mark.asyncio
async def test_trailing_blank_lines_removed_from_memory_text() -> None:
    """内存取文本同样会清理结尾空行"""
    from nonebot_plugin_larklang.__main__ import get_text, load_languages

    await load_languages()
    text = get_text("zh_hans", "broadcast", "bc.state", True)
    assert text == "功能开关：True\n最后一次广播内容："
