import traceback
from typing import Any, AsyncGenerator

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from nonebot import logger

from .exception import NoResultException, PackageNotFound
from .typing import PackageData


async def get_search_result(keyword: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://archlinux.org/packages/?sort=&q={keyword}&maintainer=&flagged=")
    return response.read()


def init_search_result(result: bytes) -> Tag:
    soup = BeautifulSoup(result)
    if (
        # soup.find("div", class_="pkglist-stats").p.string == "0 matching packages found."
        (not isinstance(stats := soup.find("div", class_="pkglist-stats"), Tag))
        or stats.p is None
        or stats.p.string == "0 matching packages found."
        or (not isinstance(tag := soup.find("table", class_="results"), Tag))
        or (not isinstance(tbody := tag.tbody, Tag))
    ):
        raise NoResultException()
    return tbody


async def get_package_page(repo: str, arch: str, package: str) -> bytes:
    url = f"https://archlinux.org/packages/{repo}/{arch}/{package}/"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PackageNotFound()
    return response.read()


def init_package_page(html: bytes) -> ResultSet[Any]:
    tag = BeautifulSoup(html).find("table", id="pkginfo")
    if not isinstance(tag, Tag):
        raise PackageNotFound()
    return tag.find_all("tr")


async def get_package_data(row: Tag) -> PackageData:
    items = row.find_all("td")
    name = items[2].string
    repo = items[1].string
    arch = items[0].string
    logger.info(f"正在获取包 {name} 的信息 ...")
    package_data = init_package_page(await get_package_page(repo.lower(), arch, name))
    # logger.debug(package_data)
    return {
        "name": name,
        "repo": repo,
        "arch": arch,
        "out_of_date": (out := bool(items[6].string)),
        "version": items[3].string,
        "description": items[4].string,
        "license": [data for data in package_data if data.find("th").string == "License(s):"][0].find("td").string,
        "last_update": items[5].string,
        "size": [data for data in package_data if data.find("th").string == "Installed Size:"][0].find("td").string,
    }


async def _search_package(keyword: str) -> AsyncGenerator[PackageData, None]:
    package_list = init_search_result(await get_search_result(keyword))
    for row in package_list.find_all("tr"):
        try:
            yield await get_package_data(row)
        except Exception:
            logger.warning(f"获取包信息时出现错误: {traceback.format_exc()}")


async def search_package(keyword: str) -> list[PackageData]:
    return [package async for package in _search_package(keyword)]
