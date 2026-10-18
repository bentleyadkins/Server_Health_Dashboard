"""Remote Linux CPU, RAM and root-disk monitoring over SSH."""

import os
import time
from pathlib import Path

import paramiko


class SSHMonitorError(RuntimeError):
    """A remote connection or metric collection failed."""


def get_remote_health(hostname: str, username: str, port: int = 22, *, key_filename: str | None = None) -> dict:
    """Return remote Linux CPU/RAM/disk percentages.

    The server must be in the local SSH known_hosts file and accessible via SSH.
    Authentication uses SSH agent/default keys or the optional key_filename.
    """
    if not hostname or not username or not (1 <= port <= 65535):
        raise ValueError("Valid hostname, username and SSH port are required")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    if known_hosts.is_file():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        client.connect(
            hostname=hostname,
            username=username,
            port=port,
            key_filename=key_filename,
            look_for_keys=True,
            allow_agent=True,
            timeout=5,
            auth_timeout=5,
            banner_timeout=5,
        )

        def command(cmd: str) -> str:
            _, stdout, stderr = client.exec_command(cmd, timeout=10)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            if stdout.channel.recv_exit_status() != 0:
                raise SSHMonitorError(f"Remote command failed: {error}")
            if not output:
                raise SSHMonitorError("Remote command returned no output")
            return output

        cpu_cmd = "awk '/^cpu / {sum=0; for(i=2;i<=NF;i++) sum+=$i; print sum, $5+$6; exit}' /proc/stat"
        total1, idle1 = map(int, command(cpu_cmd).split())
        time.sleep(1)
        total2, idle2 = map(int, command(cpu_cmd).split())
        delta = total2 - total1
        if delta <= 0:
            raise SSHMonitorError("Invalid CPU counters")
        cpu = 100 * (1 - (idle2 - idle1) / delta)

        ram_cmd = "awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} END {if(t>0) printf \"%.4f\", 100*(t-a)/t; else exit 1}' /proc/meminfo"
        ram = float(command(ram_cmd))
        disk_cmd = "df -P / | awk 'NR==2 {gsub(/%/, \"\", $5); print $5}'"
        disk = float(command(disk_cmd))

        return {
            "hostname": hostname,
            "cpu_percent": round(cpu, 2),
            "ram_percent": round(ram, 2),
            "disk_percent": round(disk, 2),
        }
    except (paramiko.SSHException, OSError, ValueError, EOFError) as exc:
        raise SSHMonitorError(f"SSH monitoring failed for {hostname}: {exc}") from exc
    finally:
        client.close()


if __name__ == "__main__":
    import json

    host = os.environ.get("SSH_HOST")
    user = os.environ.get("SSH_USER")
    if not host or not user:
        raise SystemExit("Set SSH_HOST and SSH_USER environment variables first")
    try:
        result = get_remote_health(
            host,
            user,
            int(os.environ.get("SSH_PORT", "22")),
            key_filename=os.environ.get("SSH_KEY_FILE") or None,
        )
        print(json.dumps(result, indent=2))
    except SSHMonitorError as exc:
        raise SystemExit(str(exc)) from exc
