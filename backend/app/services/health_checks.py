from __future__ import annotations

import platform
import shlex
import subprocess
import time
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from app.models import FlockAgent, FlockMetric, Node, NodeHealthCheck


def _check_config(check: NodeHealthCheck | None) -> dict:
    return check.config_json if check and check.config_json else {}


def build_health_url(node: Node, check: NodeHealthCheck | None = None) -> str:
    config = _check_config(check)
    check_type = check.check_type if check else node.health_check_type
    configured_url = config.get("url")
    configured_path = config.get("path") or config.get("health_path")
    if configured_url:
        base = str(configured_url)
    elif node.url:
        base = node.url
    else:
        scheme = "https" if check_type == "https" else "http"
        port = f":{node.port}" if node.port else ""
        base = f"{scheme}://{node.host}{port}"
    path = configured_path if configured_path is not None else node.health_check_path
    if path:
        return urljoin(base.rstrip("/") + "/", str(path).lstrip("/"))
    return base


def perform_ping_check(node: Node, check: NodeHealthCheck | None = None) -> dict:
    config = _check_config(check)
    start = time.perf_counter()
    timeout = max(check.timeout_seconds if check else node.timeout_seconds, 1)
    host = str(config.get("host") or node.host)
    args = ["ping", "-c", "1", "-W", str(timeout), host]
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
    return perform_http_like_check(node)


def perform_http_like_check(node: Node, check: NodeHealthCheck | None = None) -> dict:
    config = _check_config(check)
    url = build_health_url(node, check)
    start = time.perf_counter()
    timeout = check.timeout_seconds if check else node.timeout_seconds
    expected_status = int(config.get("expected_status_code") or node.expected_status_code)
    expected_text = config.get("expected_response_contains")
    if expected_text is None:
        expected_text = node.expected_response_contains
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.request(str(config.get("method") or "GET").upper(), url)
        latency_ms = int((time.perf_counter() - start) * 1000)
        excerpt = response.text[:500]
        if response.status_code != expected_status:
            return {
                "success": False,
                "status": "down",
                "latency_ms": latency_ms,
                "http_status": response.status_code,
                "response_excerpt": excerpt,
                "error_type": "unexpected_status",
                "error_detail": f"Expected {expected_status}, got {response.status_code}",
            }
        if expected_text and str(expected_text) not in response.text:
            return {
                "success": False,
                "status": "down",
                "latency_ms": latency_ms,
                "http_status": response.status_code,
                "response_excerpt": excerpt,
                "error_type": "missing_expected_text",
                "error_detail": f"Response missing required text: {shlex.quote(str(expected_text))}",
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
            "error_detail": f"HTTP check timed out after {timeout}s",
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


def _latest_agent_metric(db: Session | None, node: Node) -> dict | None:
    if db is None:
        return None
    agent = db.query(FlockAgent).filter(FlockAgent.node_id == node.id).first()
    if not agent and node.execution_target.startswith("flock:"):
        normalized = node.execution_target.removeprefix("flock:").strip()
        agent = (
            db.query(FlockAgent)
            .filter((FlockAgent.agent_id == normalized) | (FlockAgent.name == normalized) | (FlockAgent.hostname == normalized))
            .first()
        )
    if not agent:
        return None
    metric = db.query(FlockMetric).filter(FlockMetric.agent_id == agent.id).order_by(FlockMetric.collected_at.desc()).first()
    return metric.payload_json if metric else None


def _threshold_result(kind: str, observed: float | None, warning: float, critical: float, unit: str = "%") -> dict:
    if observed is None:
        return {"success": False, "status": "down", "error_type": f"{kind}_missing", "error_detail": f"No {kind} metric is available."}
    if observed >= critical:
        return {
            "success": False,
            "status": "down",
            "error_type": f"{kind}_critical",
            "error_detail": f"{kind.title()} usage {observed:.1f}{unit} is at or above critical threshold {critical:.1f}{unit}.",
            "response_excerpt": f"{observed:.1f}{unit}",
        }
    if observed >= warning:
        return {
            "success": False,
            "status": "degraded",
            "error_type": f"{kind}_warning",
            "error_detail": f"{kind.title()} usage {observed:.1f}{unit} is at or above warning threshold {warning:.1f}{unit}.",
            "response_excerpt": f"{observed:.1f}{unit}",
        }
    return {"success": True, "status": "healthy", "response_excerpt": f"{observed:.1f}{unit}"}


def perform_memory_check(node: Node, check: NodeHealthCheck, db: Session | None) -> dict:
    metrics = _latest_agent_metric(db, node) or {}
    observed = (metrics.get("memory") or {}).get("used_percent")
    config = _check_config(check)
    return _threshold_result("memory", float(observed) if observed is not None else None, float(config.get("warning_percent") or 80), float(config.get("critical_percent") or 90))


def perform_disk_check(node: Node, check: NodeHealthCheck, db: Session | None) -> dict:
    metrics = _latest_agent_metric(db, node) or {}
    config = _check_config(check)
    path = str(config.get("path") or "/")
    disks = (metrics.get("disk") or {}).get("filesystems") or []
    match = next((item for item in disks if item.get("mount") == path), disks[0] if disks else None)
    observed = match.get("used_percent") if match else None
    return _threshold_result("disk", float(observed) if observed is not None else None, float(config.get("warning_percent") or 80), float(config.get("critical_percent") or 90))


def perform_network_check(node: Node, check: NodeHealthCheck, db: Session | None) -> dict:
    metrics = _latest_agent_metric(db, node) or {}
    config = _check_config(check)
    interfaces = (metrics.get("network") or {}).get("interfaces") or []
    configured = config.get("interface")
    selected = next((item for item in interfaces if configured and item.get("name") == configured), None)
    selected = selected or next((item for item in interfaces if item.get("name") != "lo"), interfaces[0] if interfaces else None)
    if not selected:
        return {"success": False, "status": "down", "error_type": "network_missing", "error_detail": "No network interface metric is available."}
    rx_drop = int(selected.get("rx_drop") or 0)
    tx_drop = int(selected.get("tx_drop") or 0)
    drop_limit = int(config.get("drop_threshold") or 0)
    if rx_drop + tx_drop > drop_limit:
        return {
            "success": False,
            "status": "degraded",
            "error_type": "network_drops",
            "error_detail": f"{selected.get('name')} has {rx_drop + tx_drop} dropped packets.",
            "response_excerpt": str(selected),
        }
    return {"success": True, "status": "healthy", "response_excerpt": str(selected)[:500]}


def run_health_check(node: Node, check: NodeHealthCheck | None = None, db: Session | None = None) -> dict:
    check_type = check.check_type if check else node.health_check_type
    if check_type == "ping":
        return perform_ping_check(node, check)
    if check_type in {"http", "https", "api"}:
        return perform_http_like_check(node, check)
    if check and check_type == "memory":
        return perform_memory_check(node, check, db)
    if check and check_type == "disk":
        return perform_disk_check(node, check, db)
    if check and check_type == "network":
        return perform_network_check(node, check, db)
    return perform_http_like_check(node, check)
