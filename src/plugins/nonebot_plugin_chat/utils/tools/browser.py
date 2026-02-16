#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from typing import Literal, Optional, Dict, Any, TypedDict
from urllib.parse import urlparse
import html2text
from nonebot_plugin_chat.types import GetTextFunc
from nonebot_plugin_htmlrender import get_new_page
from nonebot.log import logger
import re

from ..url_validator import is_internal_url


class BrowseResult(TypedDict):
    """网页浏览结果"""

    success: bool
    url: str
    title: Optional[str]
    content: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]


def _clean_markdown(markdown: str) -> str:
    """清理Markdown文本"""
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"[ \t]+$", "", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"\[([^]]+)]\s+\(([^)]+)\)", r"[\1](\2)", markdown)
    markdown = re.sub(r"\[([^]]+)]\(\s*\)", r"\1", markdown)

    return markdown.strip()


async def _get_meta_content(page, name: str) -> Optional[str]:
    """获取meta标签内容"""
    try:
        return await page.evaluate(f"""
            () => {{
                const meta = document.querySelector('meta[name="{name}"]') || 
                            document.querySelector('meta[property="og:{name}"]');
                return meta ? meta.content : null;
            }}
        """)
    except Exception as e:
        logger.exception(e)
        return None


async def _remove_unwanted_elements(page):
    """移除不需要的页面元素"""
    selectors_to_remove = [
        "nav",
        "header",
        "footer",  # 导航元素
        ".advertisement",
        ".ads",
        "#ads",  # 广告
        ".popup",
        ".modal",
        ".overlay",  # 弹窗
        ".cookie-notice",
        ".gdpr",  # Cookie提示
        ".sidebar",
        ".social-share",  # 侧边栏和分享按钮
        'iframe[src*="youtube"]',
        'iframe[src*="google"]',  # 嵌入内容
    ]

    for selector in selectors_to_remove:
        try:
            await page.evaluate(f"() => {{ document.querySelectorAll('{selector}').forEach(el => el.remove()) }}")
        except Exception as e:
            logger.exception(e)
            pass


async def _extract_main_content(page) -> str:
    """提取页面主要内容"""
    # 尝试查找主要内容区域
    main_selectors = [
        "main",
        "article",
        '[role="main"]',
        "#content",
        ".content",
        "#main-content",
        ".main-content",
        "body",
    ]

    for selector in main_selectors:
        try:
            content = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    return el ? el.innerHTML : null;
                }}
            """)
            if content:
                return content
        except Exception as e:
            logger.exception(e)
            continue

    # 如果都失败，返回body内容
    return await page.content()


class AsyncBrowserTool:
    """异步浏览器工具，用于OpenAI函数调用"""

    def __init__(
        self,
        timeout: int = 30000,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
        remove_scripts: bool = True,
        remove_styles: bool = True,
    ):
        """
        初始化浏览器工具

        Args:
            timeout: 页面加载超时时间（毫秒）
            wait_until: 等待条件 ('load', 'domcontentloaded', 'networkidle')
            remove_scripts: 是否移除JavaScript
            remove_styles: 是否移除CSS样式
        """
        self.timeout = timeout
        self.wait_until = wait_until
        self.remove_scripts = remove_scripts
        self.remove_styles = remove_styles
        self.html_converter = html2text.HTML2Text()
        self._configure_converter()

    def _configure_converter(self):
        """配置HTML到Markdown转换器"""
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.ignore_emphasis = False
        self.html_converter.body_width = 0  # 不限制行宽
        self.html_converter.protect_links = True
        self.html_converter.unicode_snob = True

    async def browse(self, url: str) -> BrowseResult:
        """
        异步浏览网页并转换为Markdown

        Args:
            url: 要访问的网页URL

        Returns:
            包含markdown内容和元数据的字典
        """
        try:
            parsed = urlparse(url)
            if is_internal_url(parsed):
                return {
                    "success": False,
                    "url": url,
                    "error": "无法访问本地资源",
                    "content": None,
                    "title": None,
                    "metadata": {},
                }
            if not parsed.scheme:
                url = f"https://{url}"
            async with get_new_page() as page:
                await page.set_extra_http_headers(
                    {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    }
                )
                response = await page.goto(url, wait_until=self.wait_until, timeout=self.timeout)
                logger.debug("页面已打开")
                # 等待页面稳定
                await page.wait_for_load_state("domcontentloaded", timeout=self.timeout)

                # 获取页面标题
                title = await page.title()

                # 获取页面元数据
                meta_description = await _get_meta_content(page, "description")
                meta_keywords = await _get_meta_content(page, "keywords")

                # 清理页面内容
                if self.remove_scripts:
                    await page.evaluate("() => { document.querySelectorAll('script').forEach(el => el.remove()) }")

                if self.remove_styles:
                    await page.evaluate(
                        "() => { document.querySelectorAll('style, link[rel=\"stylesheet\"]').forEach(el => el.remove()) }"
                    )

                # 移除不必要的元素
                await _remove_unwanted_elements(page)

                # 获取主要内容
                content_html = await _extract_main_content(page)

                # 转换为Markdown
                markdown_content = self._html_to_markdown(content_html)
                markdown_content = _clean_markdown(markdown_content)
                await page.close()
            return {
                "success": True,
                "url": url,
                "title": title,
                "content": markdown_content,
                "error": None,
                "metadata": {
                    "description": meta_description,
                    "keywords": meta_keywords,
                    "status_code": response.status if response else None,
                    "content_length": len(markdown_content),
                },
            }

        except Exception as e:
            return {"success": False, "url": url, "error": str(e), "content": None, "title": None, "metadata": {}}

    def _html_to_markdown(self, html: str) -> str:
        """将HTML转换为Markdown"""
        return self.html_converter.handle(html)


browser_tool = AsyncBrowserTool()


# f"""- URL: {result['url']}
# - 请求状态: {result['metadata']['status_code']}
# - 页面简介: {result['metadata']['description']}
# - 关键词: {result['metadata']['keywords']}
# - 内容长度: {result['metadata']['content_length']}

# # {result['title']}

# {result['content']}"""


async def browse_webpage(url: str, get_text: GetTextFunc) -> str:
    logger.info(f"Moonlark 正在访问: {url}")
    result = await browser_tool.browse(url)
    if result["success"]:
        return await get_text(
            "browse_webpage.success",
            result["url"],
            result["metadata"]["status_code"],
            result["metadata"]["description"],
            result["metadata"]["keywords"],
            result["metadata"]["content_length"],
            result["title"],
            result["content"],
        )
    else:
        return await get_text("browse_webpage.error", result["error"])
