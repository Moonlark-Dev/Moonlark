# https://github.com/Moonlark-Dev/XDbot2/blob/master/src/plugins/Core/plugins/progress.py#L5-L62

import datetime


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
