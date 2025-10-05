import re
from typing import List, Tuple


class MessageSplitter:
    """
    更精简、顺序清晰的消息分割器：
    - 仅把围栏代码块和 .skip/.leave 当作“不可拆分的特殊块”，其余均为普通文本。
    - 普通文本按空行分段；含 REPLY 的段落优先作为独立消息。
    - 在最终阶段确保每条消息至多一个 REPLY，必要时拆分；删除仅包含 REPLY 的消息。
    - 合并仅在最终阶段进行，且只合并不含 REPLY 的普通消息；不会合并代码块与 .skip/.leave。
    - 尝试将消息总数控制在 3 条以内（尽力而为，不做违背约束的合并或丢弃）。
    """

    def __init__(self):
        self.reply_pattern = re.compile(r"\{REPLY:\d+}")
        # 围栏代码块（反引号），多行匹配
        self.code_block_pattern = re.compile(r"^\s*```.*?^\s*```", re.MULTILINE | re.DOTALL)
        # .skip/.leave（整行）
        self.special_pattern = re.compile(r"^\s*\.(skip|leave)\s*$", re.MULTILINE | re.IGNORECASE)

    # -------- 基础识别：代码块与特殊行 --------

    def _find_code_blocks(self, text: str) -> List[Tuple[int, int]]:
        return [(m.start(), m.end()) for m in self.code_block_pattern.finditer(text)]

    def _in_any_block(self, pos: int, blocks: List[Tuple[int, int]]) -> bool:
        for s, e in blocks:
            if s <= pos < e:
                return True
        return False

    def _find_special_lines(self, text: str, code_blocks: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        ranges = []
        for m in self.special_pattern.finditer(text):
            if self._in_any_block(m.start(), code_blocks):
                continue
            # 扩展到整行
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            ranges.append((line_start, line_end))
        return ranges

    def _segments(self, text: str) -> List[Tuple[str, str]]:
        """
        将文本切分为有序段：
        - ('code', code_text)
        - ('special', special_line_text)
        - ('normal', normal_text)
        """
        if not text:
            return []

        code_blocks = self._find_code_blocks(text)
        special_lines = self._find_special_lines(text, code_blocks)

        # 汇总所有特殊区间并排序
        specials = [(s, e, "code") for s, e in code_blocks] + [(s, e, "special") for s, e in special_lines]
        specials.sort(key=lambda x: x[0])

        segments: List[Tuple[str, str]] = []
        last = 0
        for s, e, t in specials:
            if last < s:
                segments.append(("normal", text[last:s]))
            segments.append((t, text[s:e]))
            last = e
        if last < len(text):
            segments.append(("normal", text[last:]))

        return segments

    # -------- 普通文本 -> 消息（初步） --------

    def _split_normal_into_paragraphs(self, text: str) -> List[str]:
        """
        以空行分段；保留行内缩进与内容，不剥离空格。
        """
        # 将连续空行作为分隔符；两端空白行不产生空段
        parts = re.split(r"(?:\r?\n\s*){2,}", text.strip("\n"))
        # 过滤纯空白段，但保留原有行内空格
        paragraphs = [p for p in parts if p.strip()]
        return paragraphs

    def _build_normal_messages(self, text: str) -> List[Tuple[str, str]]:
        """
        将普通文本构造成消息（初步）：
        - 含 REPLY 的段落独立为一个消息；
        - 其他段落聚合。
        返回 [('normal', text), ...]
        """
        paragraphs = self._split_normal_into_paragraphs(text)
        messages: List[Tuple[str, str]] = []

        buf: List[str] = []
        for p in paragraphs:
            if self.reply_pattern.search(p):
                if buf:
                    messages.append(("normal", "\n\n".join(buf)))
                    buf = []
                messages.append(("normal", p))
            else:
                buf.append(p)
        if buf:
            messages.append(("normal", "\n\n".join(buf)))
        return messages

    # -------- REPLY 规范化：每条 ≤ 1 个 REPLY --------

    def _normalize_replies(self, messages: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        对 'normal' 消息保证：
        - 若 0 个 REPLY：保留
        - 若 1 个 REPLY：若除 REPLY 外无内容则丢弃，否则保留
        - 若 >=2 个 REPLY：拆分为多条，每条至多一个 REPLY；仅 REPLY 的段落丢弃
        代码块与特殊消息不处理
        """
        out: List[Tuple[str, str]] = []

        for mtype, text in messages:
            if mtype != "normal":
                if text.strip():
                    out.append((mtype, text))
                continue

            matches = list(self.reply_pattern.finditer(text))
            if not matches:
                if text.strip():
                    out.append((mtype, text))
                continue

            if len(matches) == 1:
                # 检查是否还有其他内容
                if self.reply_pattern.sub("", text).strip():
                    out.append((mtype, text))
                # 否则丢弃
                continue

            # 多个 REPLY，拆分
            prev_end = 0
            for i, m in enumerate(matches):
                # 先把 REPLY 之前的内容单独拿出
                if prev_end < m.start():
                    before = text[prev_end : m.start()].strip()
                    if before:
                        out.append((mtype, before))

                # 当前 REPLY 段，延伸到下一个 REPLY 前或末尾
                seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                reply_seg = text[m.start() : seg_end]
                if self.reply_pattern.sub("", reply_seg).strip():
                    out.append((mtype, reply_seg))
                prev_end = seg_end

        return out

    # -------- 合并与条数控制 --------

    def _has_reply(self, text: str) -> bool:
        return bool(self.reply_pattern.search(text))

    def _merge_short_normals(self, messages: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        仅合并相邻、都为 normal 且都不含 REPLY 的消息。
        合并策略（温和）：
        - 若当前很短(<50)，且合并后仍较短(<100)，则合并。
        """
        merged: List[Tuple[str, str]] = []
        i = 0
        while i < len(messages):
            mtype, text = messages[i]
            if (
                i + 1 < len(messages)
                and mtype == "normal"
                and messages[i + 1][0] == "normal"
                and not self._has_reply(text)
                and not self._has_reply(messages[i + 1][1])
            ):
                if len(text) < 50 and len(text) + len(messages[i + 1][1]) < 100:
                    merged.append(("normal", (text + "\n\n" + messages[i + 1][1])))
                    i += 2
                    continue
            merged.append((mtype, text))
            i += 1
        return merged

    def _enforce_cap_best_effort(self, messages: List[Tuple[str, str]], cap: int = 3) -> List[Tuple[str, str]]:
        """
        尽力把总条数压到 cap：
        - 仅尝试合并相邻 normal 且不含 REPLY 的消息（安全）。
        - 不合并 code/special，也不跨越它们合并。
        - 不丢弃消息；若无法进一步合并则保持现状。
        """
        if len(messages) <= cap:
            return messages

        # 尝试更积极合并：只要相邻 normal 且都不含 REPLY，就合并，直到不再下降或达到 cap
        changed = True
        while changed and len(messages) > cap:
            changed = False
            new_list: List[Tuple[str, str]] = []
            i = 0
            while i < len(messages):
                if (
                    i + 1 < len(messages)
                    and messages[i][0] == "normal"
                    and messages[i + 1][0] == "normal"
                    and not self._has_reply(messages[i][1])
                    and not self._has_reply(messages[i + 1][1])
                ):
                    new_list.append(("normal", messages[i][1] + "\n\n" + messages[i + 1][1]))
                    i += 2
                    changed = True
                else:
                    new_list.append(messages[i])
                    i += 1
            messages = new_list

        return messages

    # -------- 主流程 --------

    def split_message(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []

        # 1) 切分为 code/special/normal 段
        segs = self._segments(text)

        # 2) 普通段 -> 初步消息；特殊段保持独立
        messages: List[Tuple[str, str]] = []
        for mtype, seg in segs:
            if mtype == "normal":
                messages.extend(self._build_normal_messages(seg))
            elif mtype == "special":
                s = seg.strip()
                if s:
                    messages.append(("special", s))
            else:  # code
                messages.append(("code", seg))

        # 3) 规范 REPLY（仅 normal）
        messages = self._normalize_replies(messages)

        # 4) 合并短 normal（不含 REPLY）
        messages = self._merge_short_normals(messages)

        # 5) 尽力控制总条数到 3（安全合并，不合并 code/special/含 REPLY）
        messages = self._enforce_cap_best_effort(messages, cap=3)

        # 6) 输出
        result = [txt.replace("\n\n", "\n") if type_ == "normal" else txt for type_, txt in messages if txt.strip()]
        return result


splitter = MessageSplitter()


if __name__ == "__main__":
    print(splitter.split_message("""                                                  喵？三角洲听起来问题挺多的样子

玩游戏遇到各种屏幕问题真是让人头大喵~"""))