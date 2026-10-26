from __future__ import annotations

import json
import logging
import os
import platform
import socket
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_agent_settings
from app.services.flock_policy import FlockPolicyError, authorize_command, policy_timeout

logger = logging.getLogger(__name__)
settings = get_agent_settings()


def _server_url() -> str:
    return settings.flock_server_url.rstrip("/")


def _state_path() -> Path:
    return Path(settings.flock_agent_state_path)


def _load_state() -> dict[str, Any] | None:
    path = _state_path()
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    try:
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("state must be a regular file, not a symlink")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
        with os.fdopen(fd, "r") as state_file:
            metadata = os.fstat(state_file.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise ValueError("state must be a private regular file (mode 0600)")
            if metadata.st_uid != os.geteuid():
                raise ValueError("state must be owned by the agent account")
            state = json.load(state_file)
        if not isinstance(state, dict) or not all(isinstance(state.get(key), str) and state[key] for key in ("agent_id", "agent_token")):
            raise ValueError("state is missing its agent identity or credential")
        return state
    except Exception as exc:
        # Never turn a damaged/insecure credential file into a fresh enrollment.
        raise RuntimeError(f"Unable to securely load Flock state at {path}; restore valid private state or request administrator recovery") from exc


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".flock-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as state_file:
            os.fchmod(state_file.fileno(), 0o600)
            json.dump(state, state_file, indent=2)
            state_file.flush()
            os.fsync(state_file.fileno())
        # Replaces the directory entry, never follows a destination symlink.
        os.replace(temporary_path, path)
    finally:
        Path(temporary_path).unlink(missing_ok=True)


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


def _execute(command: str, timeout_seconds: int, policy: Any = None) -> tuple[int, str]:
    try:
        args = authorize_command(policy, command)
        if type(timeout_seconds) is not int or timeout_seconds < 1:
            raise FlockPolicyError("Task timeout must be a positive integer")
        timeout_seconds = min(timeout_seconds, policy_timeout(policy))
        completed = subprocess.run(
            args,
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
        return completed.returncode, output
    except FlockPolicyError as exc:
        return 126, f"Flock policy denied command: {exc}"
    except subprocess.TimeoutExpired:
        return 124, f"Execution timed out after {timeout_seconds} seconds."
    except FileNotFoundError as exc:
        return 127, str(exc)
    except Exception as exc:
        return 1, str(exc)


def _execute_task(task: dict[str, Any]) -> tuple[int, str]:
    if task.get("task_type") != "command":
        return 126, "Flock policy denied unsupported task type"
    # Never fall back to the heartbeat policy: it may predate a revocation.
    # Older brokers without a claim-time policy snapshot fail closed.
    return _execute(task.get("command"), task.get("timeout_seconds"), task.get("policy"))


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
                policy = heartbeat.get("policy") or {}
                task = _claim_task(client, state)
                if task:
                    logger.info("Executing Flock task %s", task["id"])
                    if task.get("task_type") == "unenroll":
                        _submit_result(client, state, int(task["id"]), 0, "Flock agent unenrolled and local state removed.")
                        _remove_state()
                        logger.info("Flock agent unenrolled; exiting.")
                        return
                    exit_code, output = _execute_task(task)
                    _submit_result(client, state, int(task["id"]), exit_code, output)
                time.sleep(int(policy.get("heartbeat_interval_seconds") or 10))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.error("Flock agent credentials were rejected; restore valid state at %s or request administrator recovery. Enrollment tokens cannot replace an existing identity.", _state_path())
                else:
                    logger.warning("Flock agent HTTP error: %s", exc)
                time.sleep(5)
            except Exception as exc:
                logger.warning("Flock agent loop error: %s", exc)
                time.sleep(5)


if __name__ == "__main__":
    run_agent()
