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


def _system_metadata() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
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
        completed = subprocess.run(
            shlex.split(command),
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
