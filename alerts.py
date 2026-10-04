import os
import time
from datetime import datetime
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

def check_alerts(cpu_percent, ram_percent, disk_percent):
    alerts = []

    metrics = {
        "CPU": cpu_percent,
        "RAM": ram_percent,
        "Disk": disk_percent
    }

    for name, percent in metrics.items():
        status = get_status(percent)

        if status == "critical":
            alerts.append(f"CRITICAL: {name} usage is {percent}%")
        elif status == "warning":
            alerts.append(f"WARNING: {name} usage is {percent}%")

    if not alerts:
        alerts.append("System metrics are currently within normal ranges.")

    return alerts

def get_system_health():
    """
    Collect current system health information.
    """

    # CPU and RAM
    cpu_percent = psutil.cpu_percent(interval=1)
    ram_percent = psutil.virtual_memory().percent

    # Disk information
    disk_path = os.path.abspath(os.sep)
    disk = psutil.disk_usage(disk_path)
    disk_percent = disk.percent
    disk_remaining_gb = disk.free / (1024 ** 3)

    # System uptime
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours = uptime_seconds / 3600

    # Current timestamp
    timestamp = datetime.now().isoformat()

    # Current user
    users = psutil.users()
    current_user = users[0].name if users else "System"

    # Alerts
    alerts = []

    if cpu_percent >= WARNING_THRESHOLD:
        alerts.append(f"CPU usage is high: {cpu_percent}%")

    if ram_percent >= WARNING_THRESHOLD:
        alerts.append(f"RAM usage is high: {ram_percent}%")

    if disk_percent >= WARNING_THRESHOLD:
        alerts.append(f"Disk usage is high: {disk_percent}%")

    if not alerts:
        alerts.append("System metrics are currently within normal ranges.")

    return {
        "timestamp": timestamp,
        "user": current_user,
        "uptime_hours": round(uptime_hours, 2),
        "cpu_percent": cpu_percent,
        "cpu_status": get_status(cpu_percent),
        "ram_percent": ram_percent,
        "ram_status": get_status(ram_percent),
        "disk_percent": disk_percent,
        "disk_status": get_status(disk_percent),
        "disk_remaining_gb": round(disk_remaining_gb, 2),
        "alerts": alerts
    }
