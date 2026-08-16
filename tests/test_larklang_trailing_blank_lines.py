"""larklang 结尾空行清理测试

get_text() 返回的文本应自动删除结尾的空行（含仅含空白字符的行），
避免 YAML 块标量（`|`）保留的换行符导致消息末尾出现多余空行。
"""


def test_remove_trailing_blank_lines() -> None:
    from nonebot_plugin_larklang.__main__ import remove_trailing_blank_lines

    # 普通结尾换行
    assert remove_trailing_blank_lines("hello\n") == "hello"
    # 多个结尾空行
    assert remove_trailing_blank_lines("hello\n\n\n") == "hello"
    # 仅含空白字符的空行
    assert remove_trailing_blank_lines("hello\n  \n\t\n") == "hello"
    # 无结尾空行，保持不变
    assert remove_trailing_blank_lines("hello") == "hello"
    # 中间空行不受影响
    assert remove_trailing_blank_lines("line1\n\nline2\n") == "line1\n\nline2"
    # 全空文本
    assert remove_trailing_blank_lines("") == ""
    assert remove_trailing_blank_lines("\n\n") == ""
