from __future__ import annotations

import platform
import shlex
import subprocess
import time
from urllib.parse import urljoin

import httpx

from app.models import Node


def build_health_url(node: Node) -> str:
    if node.url:
        base = node.url
    else:
        scheme = "https" if node.health_check_type == "https" else "http"
        port = f":{node.port}" if node.port else ""
        base = f"{scheme}://{node.host}{port}"
    if node.health_check_path:
        return urljoin(base.rstrip("/") + "/", node.health_check_path.lstrip("/"))
    return base


def perform_ping_check(node: Node) -> dict:
    start = time.perf_counter()
    timeout = max(node.timeout_seconds, 1)
    args = ["ping", "-c", "1", "-W", str(timeout), node.host]
    if platform.system().lower().startswith("darwin"):
        args = ["ping", "-c", "1", "-W", str(timeout * 1000), node.host]

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 1, check=False)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if proc.returncode == 0:
            return {"success": True, "status": "healthy", "latency_ms": latency_ms}
        error_detail = (proc.stderr or proc.stdout or "ping failed").strip()
        return {
            "success": False,
            "status": "down",
            "latency_ms": latency_ms,
            "error_type": "unreachable_host",
            "error_detail": error_detail[:500],
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "status": "down",
            "error_type": "timeout",
            "error_detail": f"Ping timed out after {timeout}s",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "status": "down",
            "error_type": "runner_missing",
            "error_detail": "ping binary is not available on the monitoring host",
        }


def perform_http_check(node: Node) -> dict:
    url = build_health_url(node)
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=node.timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
        latency_ms = int((time.perf_counter() - start) * 1000)
        excerpt = response.text[:500]
        if response.status_code != node.expected_status_code:
            return {
                "success": False,
                "status": "down",
                "latency_ms": latency_ms,
                "http_status": response.status_code,
                "response_excerpt": excerpt,
                "error_type": "unexpected_status",
                "error_detail": f"Expected {node.expected_status_code}, got {response.status_code}",
            }
        if node.expected_response_contains and node.expected_response_contains not in response.text:
            return {
                "success": False,
                "status": "down",
                "latency_ms": latency_ms,
                "http_status": response.status_code,
                "response_excerpt": excerpt,
                "error_type": "missing_expected_text",
                "error_detail": f"Response missing required text: {shlex.quote(node.expected_response_contains)}",
            }
        return {
            "success": True,
            "status": "healthy",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "response_excerpt": excerpt,
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "status": "down",
            "error_type": "timeout",
            "error_detail": f"HTTP check timed out after {node.timeout_seconds}s",
        }
    except httpx.ConnectError as exc:
        return {
            "success": False,
            "status": "down",
            "error_type": "dns_or_connect_failure",
            "error_detail": str(exc)[:500],
        }
    except httpx.HTTPError as exc:
        return {
            "success": False,
            "status": "down",
            "error_type": "http_error",
            "error_detail": str(exc)[:500],
        }


def run_health_check(node: Node) -> dict:
    if node.health_check_type == "ping":
        return perform_ping_check(node)
    return perform_http_check(node)
