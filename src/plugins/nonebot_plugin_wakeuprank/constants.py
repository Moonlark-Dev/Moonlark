"""早起时间窗口常量。

``__main__`` 用它判定是否记录早起，``image`` 用它计算时间轴的跨度与刻度，
两边必须一致，所以集中放在这里而不是各自定义一份。
"""

from datetime import date, datetime, time

GLOBAL_SESSION_ID = "global"

WAKE_START = time(4, 0, 0)
WAKE_END = time(14, 0, 0)

# 时间轴跨度：4:00 - 14:00 共 10 小时（取任意同一天做差即可）
_REFERENCE_DATE = date(2000, 1, 1)
TIMELINE_SPAN_SECONDS = (
    datetime.combine(_REFERENCE_DATE, WAKE_END) - datetime.combine(_REFERENCE_DATE, WAKE_START)
).total_seconds()
# 时间轴刻度间隔（小时）：每 2 小时一个标签
TIMELINE_TICK_HOURS = 2
TIMELINE_AXIS_HOURS = tuple(range(WAKE_START.hour, WAKE_END.hour + 1, TIMELINE_TICK_HOURS))
