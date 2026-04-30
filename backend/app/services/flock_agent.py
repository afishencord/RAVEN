from __future__ import annotations

import json
import logging
import os
import platform
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _server_url() -> str:
    return settings.flock_server_url.rstrip("/")


def _state_path() -> Path:
    return Path(settings.flock_agent_state_path)


def _load_state() -> dict[str, Any] | None:
    path = _state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("Unable to read Flock agent state: %s", exc)
        return None


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _agent_name() -> str:
    return settings.flock_agent_name or os.environ.get("HOSTNAME") or socket.gethostname()


def _sudo_available() -> bool:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True, timeout=2, check=False).returncode == 0
    except Exception:
        return False


def _system_metadata() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "sudo": _sudo_available(),
    }


def _memory_metrics() -> dict[str, Any]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except Exception:
        return {}
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0)
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "used_percent": round((used / total) * 100, 2) if total else None,
    }


def _disk_metrics() -> dict[str, Any]:
    filesystems: list[dict[str, Any]] = []
    seen: set[str] = set()
    mounts = ["/"]
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            parts = line.split()
            if len(parts) > 2 and parts[2] in {"ext4", "xfs", "btrfs", "overlay", "zfs"}:
                mounts.append(parts[1])
    except Exception:
        pass
    for mount in mounts:
        if mount in seen:
            continue
        seen.add(mount)
        try:
            stat = os.statvfs(mount)
        except Exception:
            continue
        total = stat.f_blocks * stat.f_frsize
        available = stat.f_bavail * stat.f_frsize
        used = max(total - available, 0)
        filesystems.append(
            {
                "mount": mount,
                "total_bytes": total,
                "available_bytes": available,
                "used_bytes": used,
                "used_percent": round((used / total) * 100, 2) if total else None,
            }
        )
    return {"filesystems": filesystems[:16]}


def _network_metrics() -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    try:
        lines = Path("/proc/net/dev").read_text().splitlines()[2:]
    except Exception:
        return {"interfaces": interfaces}
    for line in lines:
        name, raw = line.split(":", 1)
        parts = raw.split()
        interfaces.append(
            {
                "name": name.strip(),
                "rx_bytes": int(parts[0]),
                "rx_packets": int(parts[1]),
                "rx_errs": int(parts[2]),
                "rx_drop": int(parts[3]),
                "tx_bytes": int(parts[8]),
                "tx_packets": int(parts[9]),
                "tx_errs": int(parts[10]),
                "tx_drop": int(parts[11]),
            }
        )
    return {"interfaces": interfaces}


def _metrics() -> dict[str, Any]:
    return {
        "memory": _memory_metrics(),
        "disk": _disk_metrics(),
        "network": _network_metrics(),
        "sudo": {"available": _sudo_available()},
    }


def _enroll(client: httpx.Client) -> dict[str, Any]:
    token = settings.flock_enrollment_token
    if not token:
        raise RuntimeError("FLOCK_ENROLLMENT_TOKEN is required for first enrollment")
    response = client.post(
        _server_url() + "/enroll",
        json={
            "enrollment_token": token,
            "name": _agent_name(),
            "hostname": socket.gethostname(),
            "platform": platform.system().lower() or "linux",
            "architecture": platform.machine() or "unknown",
            "version": "dev",
            "metadata_json": _system_metadata(),
            "metrics_json": _metrics(),
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    state = {"agent_id": payload["agent_id"], "agent_token": payload["agent_token"]}
    _save_state(state)
    logger.info("Enrolled Flock agent %s", state["agent_id"])
    return state


def _headers(state: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {state['agent_token']}"}


def _heartbeat(client: httpx.Client, state: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        _server_url() + f"/agents/{state['agent_id']}/heartbeat",
        json={
            "hostname": socket.gethostname(),
            "platform": platform.system().lower() or "linux",
            "architecture": platform.machine() or "unknown",
            "version": "dev",
            "metadata_json": _system_metadata(),
            "metrics_json": _metrics(),
        },
        headers=_headers(state),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _claim_task(client: httpx.Client, state: dict[str, Any]) -> dict[str, Any] | None:
    response = client.post(
        _server_url() + f"/agents/{state['agent_id']}/tasks/claim",
        headers=_headers(state),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _execute(command: str, timeout_seconds: int) -> tuple[int, str]:
    try:
        args = shlex.split(command)
        if args and args[0] != "sudo" and hasattr(os, "geteuid") and os.geteuid() != 0 and _sudo_available():
            args = ["sudo", "-n", *args]
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
        return completed.returncode, output
    except subprocess.TimeoutExpired:
        return 124, f"Execution timed out after {timeout_seconds} seconds."
    except FileNotFoundError as exc:
        return 127, str(exc)
    except Exception as exc:
        return 1, str(exc)


def _submit_result(client: httpx.Client, state: dict[str, Any], task_id: int, exit_code: int, output: str) -> None:
    response = client.post(
        _server_url() + f"/agents/{state['agent_id']}/tasks/{task_id}/result",
        json={"exit_code": exit_code, "output": output[:8000]},
        headers=_headers(state),
        timeout=15,
    )
    response.raise_for_status()


def _remove_state() -> None:
    try:
        _state_path().unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Unable to remove Flock agent state: %s", exc)


def run_agent() -> None:
    logging.basicConfig(level=logging.INFO)
    state = _load_state()
    with httpx.Client() as client:
        while not state:
            try:
                state = _enroll(client)
            except Exception as exc:
                logger.warning("Flock enrollment failed: %s", exc)
                time.sleep(5)

        while True:
            try:
                heartbeat = _heartbeat(client, state)
                policy = heartbeat.get("policy", {})
                task = _claim_task(client, state)
                if task:
                    logger.info("Executing Flock task %s", task["id"])
                    if task.get("task_type") == "unenroll":
                        _submit_result(client, state, int(task["id"]), 0, "Flock agent unenrolled and local state removed.")
                        _remove_state()
                        logger.info("Flock agent unenrolled; exiting.")
                        return
                    exit_code, output = _execute(task["command"], int(task.get("timeout_seconds") or policy.get("task_timeout_seconds") or 60))
                    _submit_result(client, state, int(task["id"]), exit_code, output)
                time.sleep(int(policy.get("heartbeat_interval_seconds") or 10))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.error("Flock agent credentials were rejected; remove %s to re-enroll.", _state_path())
                else:
                    logger.warning("Flock agent HTTP error: %s", exc)
                time.sleep(5)
            except Exception as exc:
                logger.warning("Flock agent loop error: %s", exc)
                time.sleep(5)


if __name__ == "__main__":
    run_agent()
