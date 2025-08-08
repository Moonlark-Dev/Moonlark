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

import traceback
from typing import List, Optional
from datetime import datetime
from httpx import AsyncClient
import re
from nonebot.log import logger
from bs4 import BeautifulSoup

from .types import ParseDatetimeReturn
from nonebot_plugin_hkrpg_calendar.data_source.models import BiliGameEventInfo


async def fetch_page(url: str) -> str:
    """异步获取网页内容"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with AsyncClient(headers=headers) as client:
        response = await client.get(url)
        return response.text


def parse_time_string(time_string: str) -> Optional[datetime]:
    time_string = time_string.strip()
    if re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}$", time_string):
        return datetime.strptime(time_string, "%Y/%m/%d %H:%M")
    return None


def parse_datetime(date_str: str) -> ParseDatetimeReturn:
    """解析日期时间字符串"""
    start_time, end_time = date_str.split("~")
    return {"start_time": parse_time_string(start_time), "end_time": parse_time_string(end_time)}


def extract_text_from_element(element) -> str:
    """从HTML元素中提取纯文本"""
    if element is None:
        return ""

    # 获取所有文本，移除多余的空白
    text = element.get_text(strip=True, separator=" ")
    return " ".join(text.split())


async def parse_sr_events(url: str) -> List[BiliGameEventInfo]:
    """
    异步解析崩坏：星穹铁道活动页面

    Args:
        url: 活动页面的URL

    Returns:
        List[BiliGameEventInfo]: 活动信息列表
    """
    events = []

    try:
        # 获取页面内容
        html_content = await fetch_page(url)

        # 解析HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # 查找id="CardSelectTr"的表格
        table = soup.find("table", {"id": "CardSelectTr"})

        if not table:
            # 如果没有找到指定ID的表格，尝试查找包含活动信息的其他表格
            tables = soup.find_all("table", class_=["wikitable", "mw-collapsible"])
            for t in tables:
                # 检查表格是否包含活动相关的关键词
                table_text = t.get_text().lower()
                if "活动" in table_text or "版本" in table_text:
                    table = t
                    break

        if not table:
            print("未找到活动表格")
            return events

        # 获取所有行
        rows = table.find_all("tr")

        # 跳过表头（通常是第一行）
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])

            if len(cells) < 2:  # 确保有足够的列
                continue

            try:
                time_info = parse_datetime(extract_text_from_element(cells[0]))
                event = BiliGameEventInfo(
                    version=float(extract_text_from_element(cells[5])),
                    event_name=extract_text_from_element(cells[2]) if len(cells) > 1 else "未知活动",
                    event_type=extract_text_from_element(cells[3]) if len(cells) > 2 else "未知类型",
                    start_time=time_info["start_time"],
                    end_time=time_info["end_time"],
                )

                # 尝试提取图片URL
                img = cells[1].find("img") if len(cells) > 1 else None
                if img and img.get("src"):
                    img_url = img["src"]
                    if not img_url.startswith("http"):
                        img_url = f"https://wiki.biligame.com{img_url}"
                    event.image_url = img_url

                events.append(event)

            except Exception:
                logger.warning(f"解析行时出错: {traceback.format_exc()}")
                continue

    except Exception as e:
        logger.exception(e)

    return events


async def get_events() -> list[BiliGameEventInfo]:
    return await parse_sr_events("https://wiki.biligame.com/sr/%E6%B4%BB%E5%8A%A8%E4%B8%80%E8%A7%88")
