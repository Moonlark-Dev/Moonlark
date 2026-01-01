# https://github.com/Moonlark-Dev/XDbot2/blob/master/src/plugins/Core/plugins/progress.py#L5-L62

import datetime
from datetime import timedelta


def generate_progress_bar(percentage: float, length: int = 15) -> str:
    """生成纯文本进度条

    Args:
        percentage: 百分比 (0-100)
        length: 进度条总长度（字符数）

    Returns:
        格式如 "    [▓▓▓▓▓▓▓░░░░░░░░]" 的字符串
    """
    filled_char = "▓"
    empty_char = "░"

    # 计算填充的长度
    filled_length = int(percentage / 100 * length)
    empty_length = length - filled_length

    # 构建进度条
    bar = filled_char * filled_length + empty_char * empty_length
    return f"  [{bar}]"


def calculate_percentage_of_year() -> float:
    current_datetime = datetime.datetime.now()
    start_of_year = datetime.datetime(current_datetime.year, 1, 1)
    if current_datetime.year % 4 == 0 and (current_datetime.year % 100 != 0 or current_datetime.year % 400 == 0):
        total_seconds_in_year = 31622400  # Leap year (366 days)
    else:
        total_seconds_in_year = 31536000  # Non-leap year (365 days)
    elapsed_seconds = (current_datetime - start_of_year).total_seconds()
    percentage_complete = round((elapsed_seconds / total_seconds_in_year) * 100, 3)
    return percentage_complete


def calculate_percentage_of_month() -> float:
    current_datetime = datetime.datetime.now()
    start_of_month = datetime.datetime(current_datetime.year, current_datetime.month, 1)
    if current_datetime.month == 12:
        next_month = datetime.datetime(current_datetime.year + 1, 1, 1)
    else:
        next_month = datetime.datetime(current_datetime.year, current_datetime.month + 1, 1)
    days_in_month = (next_month - start_of_month).days
    total_seconds_in_month = days_in_month * 24 * 60 * 60
    elapsed_seconds = (current_datetime - start_of_month).total_seconds()
    percentage_complete = round((elapsed_seconds / total_seconds_in_month) * 100, 3)
    return percentage_complete


def calculate_percentage_of_day() -> float:
    current_datetime = datetime.datetime.now()
    start_of_day = datetime.datetime(current_datetime.year, current_datetime.month, current_datetime.day)
    total_seconds_in_day = 24 * 60 * 60
    elapsed_seconds = (current_datetime - start_of_day).total_seconds()
    percentage_complete = round((elapsed_seconds / total_seconds_in_day) * 100, 3)
    return percentage_complete


def get_year_progress_integer() -> int:
    """获取当前年进度的整数百分比 (0-100)"""
    return int(calculate_percentage_of_year())


def get_total_seconds_in_year(year: int) -> int:
    """获取指定年份的总秒数"""
    if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        return 31622400  # 闰年 (366 天)
    else:
        return 31536000  # 非闰年 (365 天)


def calculate_next_percentage_time(target_percentage: int) -> datetime.datetime:
    """
    计算到达指定百分比的时间点

    Args:
        target_percentage: 目标百分比 (1-100)

    Returns:
        到达该百分比的 datetime
    """
    current_year = datetime.datetime.now().year
    start_of_year = datetime.datetime(current_year, 1, 1)
    total_seconds_in_year = get_total_seconds_in_year(current_year)
    target_seconds = total_seconds_in_year * target_percentage / 100
    return start_of_year + timedelta(seconds=target_seconds)


def get_next_push_info() -> tuple[int, datetime.datetime]:
    """
    获取下次推送信息

    Returns:
        (下次推送的百分比, 下次推送的时间)
    """
    current_percentage = get_year_progress_integer()
    next_percentage = current_percentage + 1

    if next_percentage > 100:
        # 已到年末，返回下一年的 1%
        next_year = datetime.datetime.now().year + 1
        start_of_next_year = datetime.datetime(next_year, 1, 1)
        total_seconds_in_next_year = get_total_seconds_in_year(next_year)
        target_seconds = total_seconds_in_next_year / 100
        return (1, start_of_next_year + timedelta(seconds=target_seconds))

    return (next_percentage, calculate_next_percentage_time(next_percentage))
