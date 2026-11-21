"""COMMAND_PREFIX：LarkLang 填充 {__prefix__} 时使用的指令前缀配置。"""

import pytest
from pydantic import ValidationError


def test_prefix_defaults_to_unset() -> None:
    """未配置 COMMAND_PREFIX 时保持原有行为：使用 COMMAND_START 的第一个前缀"""
    from nonebot_plugin_larklang.config import Config

    config = Config(command_start=["/", "#"])
    assert config.command_prefix is None
    assert (config.command_prefix or config.command_start[0]) == "/"


def test_prefix_must_be_in_command_start() -> None:
    """COMMAND_PREFIX 必须属于 COMMAND_START"""
    from nonebot_plugin_larklang.config import Config

    assert Config(command_start=["/", "#"], command_prefix="#").command_prefix == "#"

    with pytest.raises(ValidationError):
        Config(command_start=["/"], command_prefix="#")


def test_empty_prefix_means_unset() -> None:
    """`.env` 里留空的 COMMAND_PREFIX= 视为未设置，不应导致启动失败"""
    from nonebot_plugin_larklang.config import Config

    assert Config(command_start=["/"], command_prefix="").command_prefix is None
    assert Config(command_start=["/"], command_prefix="  ").command_prefix is None


def test_only_one_prefix_allowed() -> None:
    """COMMAND_PREFIX 只能设置一个前缀"""
    from nonebot_plugin_larklang.config import Config

    with pytest.raises(ValidationError):
        Config(command_start=["/", "#"], command_prefix=["/", "#"])


def test_builtin_format_uses_config_prefix() -> None:
    """builtin_format 中的 __prefix__ 与配置保持一致"""
    from nonebot_plugin_larklang.__main__ import builtin_format, config

    assert builtin_format["__prefix__"] == (config.command_prefix or config.command_start[0])


@pytest.mark.asyncio
async def test_text_fills_configured_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """{__prefix__} 会按配置的前缀填充"""
    from nonebot_plugin_larklang import __main__ as main

    await main.load_languages()
    monkeypatch.setitem(main.builtin_format, "__prefix__", "#")

    assert "#lang view <语言>" in main.get_text("zh_hans", "larklang", "lang.list", "")
