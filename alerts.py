import os
import psutil


WARNING_THRESHOLD = 80
CRITICAL_THRESHOLD = 90


def get_status(percent):
    if percent >= CRITICAL_THRESHOLD:
        return "critical"
    elif percent >= WARNING_THRESHOLD:
        return "warning"
    else:
        return "healthy"


def get_system_health():
    cpu_percent = psutil.cpu_percent(interval=1)
    ram_percent = psutil.virtual_memory().percent
    user = psutil.users()
    net_if_addrs = psutil.net_if_addrs()
    disk_path = os.path.abspath(os.sep)
    disk_percent = psutil.disk_usage(disk_path).percent

    return {
        "user": user[0].name if user else "System",
        "net_if_stats": net_if_addrs,
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "disk_percent": disk_percent
    }