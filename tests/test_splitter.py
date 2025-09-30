import pytest
from nonebug import App


@pytest.mark.asyncio
async def test_message_splitter(app: App):
    from nonebot_plugin_chat.utils import splitter

    # 测试用例1: 代码块独立成消息
    test_text1 = """开始
```python
print("hello")
```
结束"""
    result1 = splitter.split_message(test_text1)
    assert len(result1) == 3
    assert "```python" in result1[1]
    assert "print" in result1[1]

    # 测试用例2: .skip 和 .leave 独立成消息
    test_text2 = """开始
.skip
中间内容
.leave
结束"""
    result2 = splitter.split_message(test_text2)
    assert len(result2) == 5
    assert any('.skip' in msg for msg in result2)
    assert any('.leave' in msg for msg in result2)

    # 测试用例3: 单 REPLY 标签限制
    test_text3 = """开始 {REPLY:111} 内容1 {REPLY:222} 内容2"""
    result3 = splitter.split_message(test_text3)
    for msg in result3:
        reply_count = len(splitter.reply_pattern.findall(msg))
        assert reply_count <= 1

    # 测试用例4: REPLY 标签必须伴随其他内容
    test_text4 = """开始 {REPLY:111}
内容1
{REPLY:222}
内容2
{REPLY:333}"""
    result4 = splitter.split_message(test_text4)
    for msg in result4:
        if splitter.reply_pattern.search(msg):
            text_without_reply = splitter.reply_pattern.sub('', msg).strip()
            assert len(text_without_reply) > 0

    # 测试用例5: 代码块内容保持原样（包括内部的特殊内容）
    test_text5 = """```javascript
console.log("hello");
    console.log("indented");
.skip
{REPLY:123}
```"""
    result5 = splitter.split_message(test_text5)
    assert len(result5) == 1  # 整个代码块应该是一条消息
    code_block = result5[0]
    assert ".skip" in code_block
    assert "{REPLY:123}" in code_block
    assert "    console.log" in code_block  # 保持缩进

    # 测试用例6: 去除行首空格（代码块除外）
    test_text6 = """    有缩进的文本
    另一行缩进
```python
    保持缩进的代码
```
    更多普通文本"""
    result6 = splitter.split_message(test_text6)
    for msg in result6:
        if "```" not in msg:  # 非代码块
            for line in msg.split('\n'):
                if line.strip():  # 非空行
                    assert not line.startswith(' ') and not line.startswith('\t')

    # 测试用例7: 复杂场景综合测试
    test_text7 = """开始 {REPLY:111}
    普通段落1

    ```python
    def test():
        .skip
        return "hello"
    ```

    - 列表项1
    - 列表项2

    .skip
    详细说明 {REPLY:222}

    中间内容
    .leave
    结束 {REPLY:333}"""

    result7 = splitter.split_message(test_text7)

    # 验证基本要求
    for msg in result7:
        # 检查 REPLY 标签数量
        reply_count = len(splitter.reply_pattern.findall(msg))
        assert reply_count <= 1

        # 检查特殊命令是否独立
        if splitter.special_pattern.search(msg) and '```' not in msg:
            # 特殊命令行应该独立成消息
            lines = msg.strip().split('\n')
            assert len(lines) == 1 or (len(lines) > 1 and all(not line.strip() for line in lines[1:]))

    # 测试用例8: 空消息过滤
    test_text8 = """{REPLY:111}

.skip

.leave
{REPLY:222}"""
    result8 = splitter.split_message(test_text8)
    # 所有只有 REPLY 标签没有内容的消息应该被过滤掉
    for msg in result8:
        assert msg.strip()

    # 测试用例9: 多个 REPLY 标签的正确分割
    test_text9 = """第一段 {REPLY:1} 内容1 {REPLY:2} 内容2 {REPLY:3} 内容3"""
    result9 = splitter.split_message(test_text9)
    assert len(result9) >= 3  # 应该至少分成3条消息

    # 测试用例10: 段落分割逻辑
    test_text10 = """段落1

段落2

段落3

段落4

段落5"""
    result10 = splitter.split_message(test_text10)
    # 应该按段落数适当分割，每2-3个段落一条消息
    assert 2 <= len(result10) <= 3

    print("所有测试用例通过!")
