import re
from typing import List, Tuple
import pytest


class MessageSplitter:
    def __init__(self):
        # 匹配 {REPLY:\d+} 的正则表达式
        self.reply_pattern = re.compile(r"\{REPLY:\d+\}")
        # 匹配代码块的正则表达式
        self.code_block_pattern = re.compile(r"^\s*```.*?^\s*```", re.MULTILINE | re.DOTALL)
        # 匹配 .skip 和 .leave 文本
        self.special_pattern = re.compile(r"^\s*\.(skip|leave)\s*$", re.MULTILINE | re.IGNORECASE)

    def _identify_special_blocks(self, text: str) -> List[Tuple[int, int, str]]:
        """识别特殊块（代码块、.skip、.leave）的位置和类型"""
        blocks = []

        # 首先识别代码块
        code_blocks = []
        for match in self.code_block_pattern.finditer(text):
            code_blocks.append((match.start(), match.end()))
            blocks.append((match.start(), match.end(), "code_block"))

        # 识别 .skip 和 .leave 文本，但要排除在代码块内部的
        for match in self.special_pattern.finditer(text):
            # 检查这个匹配是否在任何一个代码块内部
            inside_code_block = False
            for code_start, code_end in code_blocks:
                if code_start <= match.start() < code_end:
                    inside_code_block = True
                    break

            if not inside_code_block:
                # 找到包含这个特殊文本的完整行
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                blocks.append((line_start, line_end, "special"))

        # 按起始位置排序
        blocks.sort(key=lambda x: x[0])
        return blocks

    def _split_text_into_segments(self, text: str) -> List[Tuple[str, str]]:
        """将文本分割成普通文本和特殊块的混合列表"""
        special_blocks = self._identify_special_blocks(text)
        segments = []
        last_pos = 0

        for start, end, block_type in special_blocks:
            # 添加特殊块之前的内容
            if last_pos < start:
                normal_text = text[last_pos:start]
                segments.append(("normal", normal_text))

            # 添加特殊块
            special_text = text[start:end]
            segments.append((block_type, special_text))
            last_pos = end

        # 添加最后的内容
        if last_pos < len(text):
            normal_text = text[last_pos:]
            segments.append(("normal", normal_text))

        return segments

    def _process_normal_text(self, text: str) -> List[str]:
        """处理普通文本：去除行首空格并按段落分割"""
        # 去除所有行首的空格
        cleaned_text = "\n".join(line.lstrip() for line in text.split("\n"))

        if not cleaned_text.strip():
            return []

        # 按空行分割段落
        paragraphs = re.split(r"\n\s*\n", cleaned_text)
        messages = []
        current_message = []
        current_paragraph_count = 0

        for paragraph in paragraphs:
            if not paragraph.strip():
                continue

            # 检查段落中是否包含 REPLY 标签
            reply_matches = list(self.reply_pattern.finditer(paragraph))

            if len(reply_matches) > 1:
                # 如果段落中有多个 REPLY 标签，需要进一步分割
                self._split_paragraph_with_multiple_replies(paragraph, messages)
            else:
                current_message.append(paragraph)
                current_paragraph_count += 1

                # 每3个段落形成一个消息，或者遇到 REPLY 标签时结束当前消息
                if current_paragraph_count >= 3 or (reply_matches and current_paragraph_count > 0):
                    if current_message:
                        message_text = "\n\n".join(current_message)
                        if message_text.strip():
                            messages.append(message_text)
                        current_message = []
                        current_paragraph_count = 0

        # 添加剩余的内容
        if current_message:
            message_text = "\n\n".join(current_message)
            if message_text.strip():
                messages.append(message_text)

        return messages

    def _split_paragraph_with_multiple_replies(self, paragraph: str, messages: List[str]):
        """分割包含多个 REPLY 标签的段落"""
        parts = []
        last_pos = 0

        for match in self.reply_pattern.finditer(paragraph):
            start, end = match.span()

            # 添加 REPLY 标签之前的内容
            if last_pos < start:
                before_text = paragraph[last_pos:start].strip()
                if before_text:
                    parts.append(before_text)

            # 添加 REPLY 标签和其后的内容
            reply_text = paragraph[start:end]
            after_text = paragraph[end:].split("\n")[0].strip()  # 只取同一行的内容

            if after_text:
                combined = f"{reply_text} {after_text}"
                parts.append(combined)
            else:
                # 如果 REPLY 标签后没有内容，丢弃这个标签
                pass

            last_pos = end + len(after_text) if after_text else end

        # 添加剩余内容
        if last_pos < len(paragraph):
            remaining = paragraph[last_pos:].strip()
            if remaining:
                parts.append(remaining)

        # 将每个部分作为独立的消息
        for part in parts:
            if part.strip():
                messages.append(part.strip())

    def _ensure_single_reply_per_message(self, messages: List[str]) -> List[str]:
        """确保每条消息最多只有一个 REPLY 标签且有其他内容"""
        result = []

        for message in messages:
            reply_matches = list(self.reply_pattern.finditer(message))

            if len(reply_matches) == 0:
                result.append(message)
            elif len(reply_matches) == 1:
                # 检查是否只有 REPLY 标签没有其他内容
                text_without_reply = self.reply_pattern.sub("", message).strip()
                if text_without_reply:
                    result.append(message)
                # 否则丢弃这条消息（只有 REPLY 标签没有内容）
            else:
                # 多个 REPLY 标签的情况，需要分割
                self._split_message_with_multiple_replies(message, result)

        return result

    def _split_message_with_multiple_replies(self, message: str, result: List[str]):
        """分割包含多个 REPLY 标签的消息"""
        parts = []
        last_pos = 0

        for match in self.reply_pattern.finditer(message):
            start, end = match.span()

            # 获取从上一个匹配结束到当前匹配开始的内容
            if last_pos < start:
                segment = message[last_pos:start].strip()
                if segment:
                    parts.append(segment)

            # 获取 REPLY 标签和紧随其后的内容（直到下一个 REPLY 标签或消息结束）
            reply_end = end
            if match != [i for i in self.reply_pattern.finditer(message)][-1]:
                next_match = None
                for m in self.reply_pattern.finditer(message):
                    if m.start() > end:
                        next_match = m
                        break
                if next_match:
                    reply_end = next_match.start()

            reply_segment = message[start:reply_end].strip()
            # 检查 REPLY 段是否有其他内容
            text_without_reply = self.reply_pattern.sub("", reply_segment).strip()
            if text_without_reply:
                parts.append(reply_segment)

            last_pos = reply_end

        # 添加剩余内容
        if last_pos < len(message):
            remaining = message[last_pos:].strip()
            if remaining:
                parts.append(remaining)

        result.extend(parts)

    def split_message(self, text: str) -> List[str]:
        """主函数：分割消息"""
        if not text.strip():
            return []

        # 1. 将文本分割成普通文本和特殊块的混合列表
        segments = self._split_text_into_segments(text)

        # 2. 处理每个段
        all_messages = []
        for segment_type, segment_text in segments:
            if segment_type == "normal":
                # 处理普通文本
                normal_messages = self._process_normal_text(segment_text)
                all_messages.extend(normal_messages)
            else:
                # 特殊块（代码块或.special）独立成为一条消息
                if segment_type == "code_block":
                    # 代码块保持原样
                    all_messages.append(segment_text)
                else:  # special
                    # .skip/.leave 行，去除行首空格
                    cleaned_special = "\n".join(line.lstrip() for line in segment_text.split("\n"))
                    all_messages.append(cleaned_special)

        # 3. 确保每条消息最多只有一个 REPLY 标签且有其他内容
        final_messages = self._ensure_single_reply_per_message(all_messages)

        # 4. 过滤空消息
        final_messages = [msg for msg in final_messages if msg.strip()]

        return final_messages


splitter = MessageSplitter()
