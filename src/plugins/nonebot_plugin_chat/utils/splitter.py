
import re
from typing import List, Tuple


class MessageSplitter:
    def __init__(self):
        # 匹配 {REPLY:\d+} 的正则表达式
        self.reply_pattern = re.compile(r'\{REPLY:\d+\}')
        # 匹配代码块的正则表达式
        self.code_block_pattern = re.compile(r'^```.*?^```', re.MULTILINE | re.DOTALL)
        # 匹配列表项的正则表达式
        self.list_pattern = re.compile(r'^(\s*[-*+]\s+.*|^\s*\d+\.\s+.*)', re.MULTILINE)
        # 匹配 .skip 和 .leave 文本
        self.special_pattern = re.compile(r'^\s*\.(skip|leave)\b.*', re.MULTILINE | re.IGNORECASE)

    def _identify_special_blocks(self, text: str) -> List[Tuple[int, int, str]]:
        """识别特殊块（代码块、列表、.skip、.leave）的位置和类型"""
        blocks = []

        # 识别代码块
        for match in self.code_block_pattern.finditer(text):
            blocks.append((match.start(), match.end(), 'code_block'))

        # 识别列表项
        for match in self.list_pattern.finditer(text):
            start, end = self._expand_list_block(text, match.start())
            blocks.append((start, end, 'list'))

        # 识别 .skip 和 .leave 文本
        for match in self.special_pattern.finditer(text):
            start = match.start()
            # 找到这个特殊文本的完整段落
            end = self._find_paragraph_end(text, start)
            blocks.append((start, end, 'special'))

        # 按起始位置排序并合并重叠的块
        blocks.sort(key=lambda x: x[0])
        merged_blocks = []
        for block in blocks:
            if merged_blocks and block[0] <= merged_blocks[-1][1]:
                # 合并重叠的块
                prev_start, prev_end, prev_type = merged_blocks.pop()
                new_end = max(prev_end, block[1])
                merged_blocks.append((prev_start, new_end, 'mixed'))
            else:
                merged_blocks.append(block)

        return merged_blocks

    def _expand_list_block(self, text: str, list_start: int) -> Tuple[int, int]:
        """扩展列表块到完整的列表项"""
        lines = text[list_start:].split('\n')
        end = list_start

        for i, line in enumerate(lines):
            current_pos = list_start + sum(len(lines[j]) + 1 for j in range(i))

            # 如果是空行，列表结束
            if not line.strip():
                break

            # 如果是列表项或缩进的行（属于同一个列表项）
            if (self.list_pattern.match(line) or
                    (i > 0 and line.strip() and (line.startswith('  ') or line.startswith('\t')))):
                end = current_pos + len(line)
            else:
                # 如果不是列表项且没有缩进，列表结束
                if i > 0:  # 至少已经有一个列表项
                    break

        return list_start, end

    def _find_paragraph_end(self, text: str, start: int) -> int:
        """找到段落的结束位置"""
        # 从start位置开始，找到下一个空行或文本结束
        remaining_text = text[start:]
        lines = remaining_text.split('\n')

        for i, line in enumerate(lines):
            if i > 0 and not line.strip():  # 遇到空行
                return start + sum(len(lines[j]) + 1 for j in range(i))

        return len(text)  # 没有空行，到文本结束

    def _remove_leading_spaces(self, text: str, special_blocks: List[Tuple[int, int, str]]) -> str:
        """去除非特殊块中行首的空格"""
        result = []
        last_pos = 0

        for start, end, block_type in special_blocks:
            # 添加特殊块之前的内容（去除行首空格）
            if last_pos < start:
                normal_text = text[last_pos:start]
                cleaned_text = '\n'.join(line.lstrip() for line in normal_text.split('\n'))
                result.append(cleaned_text)

            # 添加特殊块（保持原样）
            result.append(text[start:end])
            last_pos = end

        # 添加最后的内容
        if last_pos < len(text):
            normal_text = text[last_pos:]
            cleaned_text = '\n'.join(line.lstrip() for line in normal_text.split('\n'))
            result.append(cleaned_text)

        return ''.join(result)

    def _split_by_paragraphs(self, text: str, max_paragraphs: int = 3) -> List[str]:
        """按段落分割文本，确保每个消息不超过指定段落数"""
        # 首先尝试用 \n\n 分割
        paragraphs = re.split(r'\n\s*\n', text)

        if len(paragraphs) <= max_paragraphs:
            return ['\n\n'.join(paragraphs)] if paragraphs else []

        # 如果 \n\n 分割太碎，尝试用 \n 分割
        lines = text.split('\n')
        messages = []
        current_message = []
        current_line_count = 0

        for line in lines:
            # 检查是否是段落分隔
            is_paragraph_sep = not line.strip()

            if is_paragraph_sep and current_line_count > 0:
                # 如果遇到空行且当前消息已有内容，考虑结束当前消息
                if len(current_message) >= max_paragraphs * 2:  # 估计的段落数
                    messages.append('\n'.join(current_message))
                    current_message = []
                    current_line_count = 0
                    continue

            current_message.append(line)
            current_line_count += 1

            # 如果达到最大段落数的估计行数，结束当前消息
            if current_line_count >= max_paragraphs * 10:  # 假设每个段落平均10行
                messages.append('\n'.join(current_message))
                current_message = []
                current_line_count = 0

        if current_message:
            messages.append('\n'.join(current_message))

        return messages

    def _ensure_single_reply_per_message(self, messages: List[str]) -> List[str]:
        """确保每条消息最多只有一个 {REPLY:\d+} 且有其他内容"""
        result = []

        for message in messages:
            reply_matches = list(self.reply_pattern.finditer(message))

            if len(reply_matches) <= 1:
                result.append(message)
                continue

            # 如果消息中有多个 REPLY，需要分割
            last_pos = 0
            current_parts = []

            for i, match in enumerate(reply_matches):
                start, end = match.span()

                # 获取从上一个匹配到当前匹配的内容
                segment = message[last_pos:end]
                last_pos = end

                # 检查这个片段是否只有 REPLY 标签
                text_without_reply = self.reply_pattern.sub('', segment).strip()

                if text_without_reply:  # 有其他内容
                    current_parts.append(segment)
                else:
                    # 如果只有 REPLY 标签，需要与前面的内容合并
                    if current_parts:
                        current_parts[-1] += segment
                    else:
                        current_parts.append(segment)

                # 如果当前片段包含内容且不是最后一个，可以考虑分割
                if text_without_reply and i < len(reply_matches) - 1:
                    result.append(''.join(current_parts))
                    current_parts = []

            # 添加剩余内容
            if current_parts:
                remaining = message[last_pos:]
                if remaining.strip():
                    current_parts.append(remaining)
                result.append(''.join(current_parts))

        return result

    def split_message(self, text: str) -> List[str]:
        """主函数：分割消息"""
        if not text.strip():
            return []

        # 1. 识别特殊块
        special_blocks = self._identify_special_blocks(text)

        # 2. 去除非特殊块中行首的空格
        cleaned_text = self._remove_leading_spaces(text, special_blocks)

        # 3. 按段落分割
        initial_messages = self._split_by_paragraphs(cleaned_text, max_paragraphs=3)

        # 4. 确保每条消息最多只有一个 REPLY 标签且有其他内容
        final_messages = self._ensure_single_reply_per_message(initial_messages)

        # 5. 过滤空消息
        final_messages = [msg for msg in final_messages if msg.strip()]

        return final_messages

splitter = MessageSplitter()
# 使用示例
def main():


    # 测试文本
    test_text = """
这是一段测试文本。

第一段落有一些内容。
   这一行开头有空格，应该被去除。

第二段落。
{REPLY:123} 这个 REPLY 标签应该保留。

```python
def example():
    # 代码块中的空格应该保留
    print("Hello World")
```

- 这是一个列表项
- 这是另一个列表项
  这是列表项的延续内容

第三段落。
另一个 {REPLY:456} 标签。

.skip 这是一个特殊的跳过文本
应该保持完整。

第四段落。
   这里有缩进，但会被去除。
"""

    messages = splitter.split_message(test_text)

    for i, msg in enumerate(messages, 1):
        print(f"=== 消息 {i} ===")
        print(msg)
        print("=" * 50)


if __name__ == "__main__":
    main()
