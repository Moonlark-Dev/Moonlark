"""online-timer 的统计口径常量。"""

# 在线记录的保留时长。取一个月再多留一天：在线概率按 ``PROBABILITY_WINDOW_DAYS`` 的窗口
# 统计，而清理任务每天只在 2:00 跑一次，多留一天缓冲才能保证这一个月的数据总是完整的
# （否则窗口最远端那一天会随着清理时刻漂移被削掉一部分）。
RECORD_RETENTION_DAYS = 31

# 在线概率热力图（在线概率功能）的统计窗口。
PROBABILITY_WINDOW_DAYS = 30
