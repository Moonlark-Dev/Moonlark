from datetime import datetime
from typing import Awaitable, Callable
from nonebot_plugin_openai import MessageFetcher
from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter
from nonebot_plugin_openai.utils.message import generate_message

from .tools import browse_webpage, web_search, request_wolfram_alpha, search_abbreviation, get_vm_tools, is_vm_available

from ..lang import lang




class AskAISession:

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.functions = [
            AsyncFunction(
                func=browse_webpage,
                description=(
                    "访问指定 URL 并获取网页内容的 Markdown 格式文本。\n"
                    "**使用场景**:\n"
                    "- 用户提供了一个 URL 并希望你帮助分析或总结其内容\n"
                    "- 需要从某个特定网页获取详细信息来回答用户问题\n"
                    "- 在使用 web_search 获取搜索结果后，需要深入了解某个搜索结果的具体内容"
                ),
                parameters={
                    "url": FunctionParameter(
                        type="string",
                        description="要访问的网页 URL，必须包含协议前缀（http:// 或 https://）",
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=web_search,
                description=(
                    "从互联网搜索相关信息。\n"
                    "**使用场景**:\n"
                    "- 用户询问时事新闻、当前事件、特定人物或组织的信息\n"
                    "- 用户的问题涉及你知识库之外的最新数据或事实\n"
                    "- 需要验证或补充关于某个话题的信息\n"
                    "**注意**: 使用简洁的关键词（2-5个）进行搜索，而不是完整的句子。"
                ),
                parameters={
                    "keyword": FunctionParameter(
                        type="string",
                        description="搜索关键词，使用简洁的关键词组合，多个关键词用空格分隔。例如: '量子计算 发展 2025' 而非 '量子计算在2025年有什么发展？'",
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=request_wolfram_alpha,
                description=(
                    "使用 Wolfram|Alpha 进行精确计算和数据查询。\n"
                    "**使用场景**:\n"
                    "- 数学计算：方程求解、积分、微分、矩阵运算等\n"
                    "- 单位换算：长度、重量、温度、货币等\n"
                    "- 科学计算：物理公式、化学方程、统计分析等\n"
                    "- 日期时间：计算日期差、星期几、日出日落时间等\n"
                    "**注意**: 不要自己进行复杂数学计算，使用此工具获取精确答案。"
                ),
                parameters={
                    "question": FunctionParameter(
                        type="string",
                        description="输入 Wolfram|Alpha 的查询内容，可以是数学表达式、自然语言（推荐使用英文）或 LaTeX 格式。",
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=search_abbreviation,
                description=(
                    "查询拼音首字母缩写或网络用语缩写的含义。\n"
                    "**使用场景**:\n"
                    "- 遇到不理解的字母缩写，如 yyds、xswl、nsdd 等中文网络用语\n"
                    "- 用户询问某个缩写的意思"
                ),
                parameters={
                    "text": FunctionParameter(
                        type="string",
                        description="要查询的缩写文本，如 'yyds'、'xswl' 等",
                        required=True,
                    )
                },
            ),
        ]
        # 如果 VM 服务可用，添加 VM 相关工具
        if is_vm_available():
            self.functions.extend(get_vm_tools())
        

    async def ask_ai(self, prompt: str) -> str:
        fetcher = await MessageFetcher.create(
            [
                generate_message(await lang.text("prompt_agent.system", self.user_id, datetime.now().isoformat())),
                generate_message(prompt, "user")
            ],
            False,
            functions=self.functions,
            identify="Ask AI"
        )
        return await fetcher.fetch_last_message()
    
