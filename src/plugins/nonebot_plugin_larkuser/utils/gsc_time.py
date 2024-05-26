# 1984-01-01 00:00:00
GALACTIC_YEAR = 441734400


def get_galactic_time(earth_time: float) -> list[int]:
    time_struct: list[float] = [1, 1, 1, 0, 0, 0]
    timestamp = earth_time - GALACTIC_YEAR
    days = timestamp // 72000
    daytime = timestamp - days * 72000
    time_struct[3] = daytime // 7200
    daytime %= 7200
    time_struct[4] = daytime // 60
    time_struct[5] = daytime % 60
    year_cycle = days // 3507
    cycle_days = days % 3507
    year_index = min(cycle_days // 350, 9)
    time_struct[0] = year_cycle * 10 + year_index
    year_days = cycle_days - year_index * 350
    month_index = min(year_days // 35, 10)
    time_struct[1] = month_index + 1
    time_struct[2] = year_days - month_index * 35
    for i in range(5):
        time_struct[i] = int(time_struct[i])
    return [round(number) for number in time_struct]
