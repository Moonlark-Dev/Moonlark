import re
from typing import List, Tuple


class MessageSplitter:
    def __init__(self):
        # 匹配 REPLY:\d+ 的正则表达式
        self.reply_pattern = re.compile(r"REPLY:\d+")
        # 匹配代码块的正则表达式
        self.code_block_pattern = re.compile(r"^\s*```.*?^\s*```", re.MULTILINE | re.DOTALL)
        # 匹配 .skip 和 .leave 文本
        self.special_pattern = re.compile(r"^\s*\.(skip|leave)\s*$", re.MULTILINE | re.IGNORECASE)
        # 匹配 Markdown 格式的正则表达式
        self.markdown_pattern = re.compile(
            r"(^\s*```.*?^\s*```|^\s*\* .*?$|^\s*> .*?$|^\s*#{1,6} .*?$)", 
            re.MULTILINE | re.DOTALL
        )

    def _identify_special_blocks(self, text: str) -> List[Tuple[int, int, str]]:
        """识别特殊块（代码块、.skip、.leave、Markdown格式）的位置和类型"""
        blocks = []
        
        # 识别代码块
        code_blocks = []
        for match in self.code_block_pattern.finditer(text):
            code_blocks.append((match.start(), match.end()))
            blocks.append((match.start(), match.end(), "markdown"))
            
        # 识别 Markdown 格式（排除代码块内的）
        for match in self.markdown_pattern.finditer(text):
            inside_code_block = False
            for code_start, code_end in code_blocks:
                if code_start <= match.start() < code_end:
                    inside_code_block = True
                    break
                    
            if not inside_code_block:
                blocks.append((match.start(), match.end(), "markdown"))
                
        # 识别 .skip 和 .leave 文本
        special_lines = []
        for match in self.special_pattern.finditer(text):
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
                special_lines.append((line_start, line_end))
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

    def _remove_leading_spaces(self, text: str) -> str:
        """去除行首空格，但保留代码块内的空格"""
        lines = text.split('\n')
        result = []
        
        in_code_block = False
        for line in lines:
            # 检查代码块开始/结束
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                result.append(line)  # 代码块标记行保持原样
            elif in_code_block:
                result.append(line)  # 代码块内内容保持原样
            else:
                result.append(line.lstrip())  # 去除行首空格
                
        return '\n'.join(result)

    def _process_normal_text(self, text: str) -> List[str]:
        """处理普通文本：按要求分割消息"""
        if not text.strip():
            return []
            
        # 去除行首空格
        cleaned_text = self._remove_leading_spaces(text)
        
        # 按段落分割
        paragraphs = [p.strip() for p in cleaned_text.split('\n\n') if p.strip()]
        if not paragraphs:
            return []
            
        messages = []
        current_message_parts = []
        reply_in_current = False
        
        for paragraph in paragraphs:
            # 检查是否包含 REPLY
            reply_matches = list(self.reply_pattern.finditer(paragraph))
            
            # 如果当前段落有 REPLY
            if reply_matches:
                # 如果当前消息已经有内容，先保存
                if current_message_parts:
                    messages.append('\n\n'.join(current_message_parts))
                    current_message_parts = []
                    reply_in_current = False
                    
                # 单独处理包含 REPLY 的段落
                # 检查 REPLY 之外是否有其他内容
                text_without_reply = self.reply_pattern.sub("", paragraph).strip()
                if text_without_reply:
                    # REPLY 和其他内容一起，可以作为一条消息
                    messages.append(paragraph)
                # 如果只有 REPLY 没有其他内容，则丢弃
            else:
                # 普通段落
                # 如果当前消息已经有 REPLY，需要新开一条消息
                if reply_in_current:
                    messages.append('\n\n'.join(current_message_parts))
                    current_message_parts = [paragraph]
                    reply_in_current = False
                else:
                    # 检查添加这个段落后是否会超过3条消息的限制
                    if len(current_message_parts) >= 2:  # 已经有2个段落，再加一个就可能超限
                        # 先保存当前消息
                        if current_message_parts:
                            messages.append('\n\n'.join(current_message_parts))
                        # 开始新消息
                        current_message_parts = [paragraph]
                    else:
                        current_message_parts.append(paragraph)
                        
        # 保存最后的消息
        if current_message_parts:
            messages.append('\n\n'.join(current_message_parts))
            
        # 合并短消息（总长度小于50字符的合并）
        merged_messages = []
        i = 0
        while i < len(messages):
            current = messages[i]
            # 如果当前消息很短，尝试与后续消息合并
            if len(current) < 50 and i + 1 < len(messages):
                next_msg = messages[i + 1]
                # 如果合并后 still 很短或者其中一个是 REPLY 消息，则合并
                if len(current + next_msg) < 100 or \
                   self.reply_pattern.search(current) or \
                   self.reply_pattern.search(next_msg):
                    merged_messages.append(current + '\n\n' + next_msg)
                    i += 2  # 跳过下一个
                else:
                    merged_messages.append(current)
                    i += 1
            else:
                merged_messages.append(current)
                i += 1
                
        return merged_messages

    def _handle_special_segments(self, segments: List[Tuple[str, str]]) -> List[str]:
        """处理特殊段（代码块、.skip/.leave）"""
        messages = []
        
        for segment_type, segment_text in segments:
            if segment_type == "normal":
                # 处理普通文本
                normal_messages = self._process_normal_text(segment_text)
                messages.extend(normal_messages)
            elif segment_type == "special":
                # .skip/.leave 独立成一条消息
                cleaned_text = self._remove_leading_spaces(segment_text)
                messages.append(cleaned_text.strip())
            else:  # markdown
                # Markdown 格式保持完整，独立成一条消息
                messages.append(segment_text)
                
        return messages

    def split_message(self, text: str) -> List[str]:
        """主函数：分割消息"""
        if not text.strip():
            return []
            
        # 1. 将文本分割成普通文本和特殊块的混合列表
        segments = self._split_text_into_segments(text)
        
        # 2. 处理特殊段
        messages = self._handle_special_segments(segments)
        
        # 3. 确保每条消息最多只有一个 REPLY 且有其他内容
        final_messages = []
        for message in messages:
            reply_matches = list(self.reply_pattern.finditer(message))
            
            if len(reply_matches) == 0:
                # 没有 REPLY，直接添加
                if message.strip():
                    final_messages.append(message)
            elif len(reply_matches) == 1:
                # 一个 REPLY，检查是否有其他内容
                text_without_reply = self.reply_pattern.sub("", message).strip()
                if text_without_reply:
                    final_messages.append(message)
                # 否则丢弃（只有 REPLY 没有其他内容）
            else:
                # 多个 REPLY，需要分割
                last_pos = 0
                for match in reply_matches:
                    start, end = match.span()
                    
                    # 添加 REPLY 之前的内容
                    if last_pos < start:
                        before_text = message[last_pos:start].strip()
                        if before_text:
                            final_messages.append(before_text)
                            
                    # 处理 REPLY 及其后的内容
                    # 获取到下一个 REPLY 或结尾的内容
                    next_start = len(message)
                    for next_match in reply_matches:
                        if next_match.start() > end:
                            next_start = next_match.start()
                            break
                            
                    reply_segment = message[start:next_start].strip()
                    # 检查 REPLY 段是否有其他内容
                    text_without_reply = self.reply_pattern.sub("", reply_segment).strip()
                    if text_without_reply:
                        final_messages.append(reply_segment)
                        
                    last_pos = next_start
                    
                # 添加剩余内容
                if last_pos < len(message):
                    remaining = message[last_pos:].strip()
                    if remaining:
                        final_messages.append(remaining)
                        
        # 4. 最终清理：过滤空消息并控制总数
        filtered_messages = [msg for msg in final_messages if msg.strip()]
        
        # 控制消息数量不超过3条（除非是 Markdown 格式）
        if len(filtered_messages) > 3:
            # 检查是否有 Markdown 格式的消息
            has_markdown = any(
                seg[0] == "markdown" 
                for seg in self._split_text_into_segments(text)
            )
            
            if not has_markdown:
                # 没有 Markdown 格式，尝试合并消息
                merged = []
                i = 0
                while i < len(filtered_messages):
                    if len(merged) >= 2 and i + 1 < len(filtered_messages):
                        # 已经有2条消息，再加一条就达到3条限制
                        # 将剩余所有消息合并为一条
                        remaining = '\n\n'.join(filtered_messages[i:])
                        merged.append(remaining)
                        break
                    else:
                        merged.append(filtered_messages[i])
                        i += 1
                        
                filtered_messages = merged
                
        return filtered_messages


splitter = MessageSplitter()
