import platform
import time
from typing import Dict, Any

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def get_windows_load_avg(sample_interval: int = 5) -> float:
    """
    计算一个类似于 Linux 上 1 分钟平均负载的参考值。
    由于 Windows 没有直接等价物，这是一个模拟值。

    参数:
        sample_interval (int): 采样间隔（秒）。更短的时间更敏感，更长的时间更平滑。

    返回:
        float: 模拟的负载值。
    """
    if not PSUTIL_AVAILABLE:
        return 0.0

    # 获取初始 CPU 时间和系统启动后的时间
    cpu_percent_start = psutil.cpu_percent(interval=None)
    # 第一次调用 cpu_percent(interval=None) 会立即返回，需要手动采样

    # 睡眠一段时间进行采样
    time.sleep(sample_interval)

    # 获取采样间隔内的平均 CPU 使用率 (一个 0-100 之间的数字)
    avg_cpu_usage = psutil.cpu_percent(interval=None)  # 这里 interval=None 是因为我们在上面手动 sleep 了

    # 获取当前正在运行的进程数
    try:
        running_processes = len(
            [p for p in psutil.process_iter(["status"]) if p.info["status"] == psutil.STATUS_RUNNING]
        )
    except:
        running_processes = 0

    # 获取 CPU 逻辑核心数量
    cpu_cores = psutil.cpu_count() or 1

    # 合成负载值：
    # 基础是缩放后的 CPU 使用率（例如，80% 的 CPU 使用率贡献 0.8 的负载单位）
    # 再加上一个由正在运行的进程数加权后的值（除以核心数是为了归一化）
    simulated_load = (avg_cpu_usage / 100) + (running_processes / cpu_cores) * 0.5

    return simulated_load


import cpuinfo


def get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    if not PSUTIL_AVAILABLE:
        return {
            "loadavg": 0.0,
            "cpu": {"usage": 0, "name": "Unknown", "freq": 0.0, "core_count": 0},
            "mem": {"used": 0, "total": 0},
            "swap": {"used": 0, "total": 0},
            "uptime": 0,
            "os_name": platform.platform(),
        }

    # 获取 CPU 信息
    cpu_usage = psutil.cpu_percent(interval=1)
    cpu_freq = psutil.cpu_freq()
    cpu_core_count = psutil.cpu_count()

    # 获取 CPU 名称
    cpu_name = ""
    try:
        cpu_name = cpuinfo.get_cpu_info()["brand_raw"]
    except:
        cpu_name = "Unknown"

    # 获取内存信息
    mem = psutil.virtual_memory()
    mem_used_gb = round(mem.used / (1024**3), 2)
    mem_total_gb = round(mem.total / (1024**3), 2)

    # 获取交换内存信息
    swap = psutil.swap_memory()
    swap_used_gb = round(swap.used / (1024**3), 2) if swap.used else 0
    swap_total_gb = round(swap.total / (1024**3), 2) if swap.total else 0

    # 获取系统启动时间
    boot_time = psutil.boot_time()
    system_uptime = time.time() - boot_time

    # 获取负载平均值
    load_avg = 0.0
    try:
        # 在 Unix 系统上可以直接获取
        load_avg_data = psutil.getloadavg()
        load_avg = load_avg_data[0]  # 1分钟平均负载
    except AttributeError:
        # 在 Windows 上使用自定义函数
        load_avg = get_windows_load_avg(1)
    except:
        load_avg = 0.0

    return {
        "loadavg": round(load_avg, 2),
        "cpu": {
            "usage": round(cpu_usage, 1),
            "name": cpu_name,
            "freq_current": round(cpu_freq.current / 1000, 2) if cpu_freq else 0.0,
            "freq_max": round(cpu_freq.max / 1000, 2) if cpu_freq else 0.0,
            "core_count": cpu_core_count,
        },
        "mem": {"used": mem_used_gb, "total": mem_total_gb},
        "swap": {"used": swap_used_gb, "total": swap_total_gb},
        "uptime": int(system_uptime),
        "os_name": platform.platform(),
    }


def get_nb_uptime(start_time: float) -> int:
    """获取 Moonlark 运行时间"""
    return int(time.time() - start_time)
