"""sticker 工具搜索结果的多行格式测试

`sticker.search_result` 在 zh_hans 中曾用单引号写成 `'...：\\n{}'`：YAML 单引号
标量里只有 `''` 是转义，`\\n` 会原样保留成「反斜杠 + n」，于是模型收到的工具结果
是一行里夹着字面量 `\\n`（en_us / zh_tw 用双引号，反而是真的换行）。
这里锁住三种语言的解析结果都是真正的换行。
"""

import glob
import os

import pytest
import yaml

LANG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "lang")
LANGS = ("zh_hans", "en_us", "zh_tw")


def _load_lang(language: str) -> dict:
    path = os.path.join(LANG_DIR, language, "chat.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("language", LANGS)
def test_sticker_search_result_uses_real_newline(language: str) -> None:
    """sticker.search_result 必须渲染成真正的换行，而不是字面量 \\n"""
    text = _load_lang(language)["sticker"]["search_result"]
    rendered = text.format("- 132: 猫猫\n- -7: 狗头")

    # 不能出现字面量「反斜杠 + n」
    assert "\\n" not in rendered
    # 必须是三行
    assert rendered.splitlines() == ["找到以下表情包：", "- 132: 猫猫", "- -7: 狗头"]


@pytest.mark.parametrize("language", LANGS)
def test_all_langs_agree_on_sticker_search_result(language: str) -> None:
    """三种语言对同一 key 的解析结果应一致（避免单双引号混用再次漂移）"""
    assert _load_lang(language)["sticker"]["search_result"] == _load_lang("zh_hans")["sticker"]["search_result"]


def test_no_literal_backslash_n_in_zh_hans_strings() -> None:
    """zh_hans 的字符串里不应残留字面量 \\n（单引号 YAML 不会把 \\n 当转义）"""
    offenders: list[str] = []
    for path in sorted(glob.glob(os.path.join(LANG_DIR, "zh_hans", "*.yaml"))):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        def walk(node: object, prefix: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{prefix}.{key}" if prefix else str(key))
            elif isinstance(node, str) and "\\n" in node:
                offenders.append(f"{os.path.basename(path)}: {prefix}")

        walk(data, "")

    assert offenders == [], f"检测到字面量 \\n（应改用双引号或块标量）: {offenders}"
