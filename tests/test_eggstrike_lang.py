"""eggstrike 语言键展开测试：info.data 不应被 larklang loader 当作叶子节点"""

from pathlib import Path

import yaml

_LANG_PATH = Path(__file__).resolve().parent.parent / "src" / "lang" / "zh_hans" / "eggstrike.yaml"


def test_eggstrike_lang_keys_expand() -> None:
    """info 下的 data 子键应展开为 info.data.*，info 本身不应成为叶子节点

    回归场景：原先使用 info.text 命名，而 larklang 的 KeysParser 会把
    任何含 text 键的 dict 当作叶子（LanguageKey），导致 info 整体被存为
    一个字符串，info.data.received 等键全部缺失。
    """
    from nonebot_plugin_larklang.loader import KeysParser

    data = yaml.safe_load(_LANG_PATH.read_text(encoding="utf-8"))
    keys = KeysParser(data, {}).get_keys()

    # info 下的键应正常展开
    assert "info.title" in keys
    assert "info.data.received" in keys
    assert "info.data.thrown" in keys
    assert "info.data.max_attack" in keys
    assert "info.data.max_received" in keys
    # info 不应被当作叶子节点（这是旧 bug 的表现）
    assert "info" not in keys
    assert "info.text.received" not in keys
    # 时间跨度键保持顶级
    assert "span_7d" in keys
    assert "span_30d" in keys
    assert "span_total" in keys
