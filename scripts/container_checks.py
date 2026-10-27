#!/usr/bin/env python3
"""Private disposable-container checks; never dispatch a command to a real agent."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

# The mounted script lives outside /app. Import only the application in the image.
sys.path.insert(0, "/app")


class CheckFailure(RuntimeError):
    """Only test-authored, credential-free diagnostic messages."""


def check(value: bool, description: str) -> None:
    if not value:
        raise CheckFailure(description)


def settings_and_passwords():
    check(os.environ.get("RAVEN_DISPOSABLE_SMOKE") == "1", "Disposable-test guard is required")
    from app.config import get_settings
    settings = get_settings()
    check(settings.database_url == "sqlite:////data/raven.db", "Unexpected database target")
    check(not settings.embedded_monitoring and not settings.openai_api_key, "Monitoring/AI must be disabled")
    check(all(len(value or "") >= 40 for value in (settings.jwt_secret_key, settings.flock_internal_token, settings.flock_enrollment_token)), "Fresh test secrets are required")
    passwords = json.loads(Path("/checks/passwords.json").read_text())
    check(set(passwords) == {"admin", "operator", "viewer"}, "Expected three test roles")
    check(all(len(password) >= 40 for password in passwords.values()), "Random role passwords are required")
    check(settings.bootstrap_admin_username == "admin" and settings.bootstrap_admin_password == passwords["admin"], "Secure bootstrap must use only the generated administrator credential")
    check(not settings.ssh_known_hosts_path, "SSH trust must not be inherited")
    return settings, passwords


def disable_checks(db):
    from app.models import Node, NodeHealthCheck
    db.query(Node).update({Node.is_enabled: False})
    db.query(NodeHealthCheck).update({NodeHealthCheck.is_enabled: False})
    db.commit()


def seed():
    settings, passwords = settings_and_passwords()
    from app.auth import get_password_hash, verify_password
    from app.database import Base, SessionLocal, engine, migrate_sqlite_schema
    from app.models import Credential, FlockPolicy, User
    from app.seed import seed_data
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()
    with SessionLocal() as db:
        check(db.query(User).count() == 0, "Refusing to seed an existing database")
        seed_data(db)
        check([(user.username, user.role) for user in db.query(User)] == [("admin", "admin")], "Secure bootstrap must create only the configured administrator")
        check(db.query(Credential).count() == 0, "Seed must not create a demo infrastructure credential")
        for role in ("operator", "viewer"):
            db.add(User(username=role, role=role, full_name=f"Disposable Docker {role}", hashed_password=get_password_hash(passwords[role])))
        db.commit()
        disable_checks(db)
        for policy in db.query(FlockPolicy):
            policy.heartbeat_interval_seconds = 1
        db.commit()
        for user in db.query(User):
            check(not verify_password(user.username + "123!", user.hashed_password), "Demo password unexpectedly enabled")
    engine.dispose()
    print("PASS: secure administrator bootstrap before listeners; random role fixtures; monitoring/AI disabled")


def ready():
    settings_and_passwords()
    import httpx
    with httpx.Client(trust_env=False, timeout=2) as client:
        for name, url in (("backend", "http://backend:8000/api/health"), ("flock", "http://flock:8000/api/health"), ("frontend", "http://frontend:3000/login")):
            deadline = time.monotonic() + 40
            last = "connection unavailable"
            while time.monotonic() < deadline:
                try:
                    response = client.get(url)
                    last = f"HTTP {response.status_code}"
                    if response.status_code == 200:
                        print(f"PASS: internal {name} readiness HTTP 200", flush=True)
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            else:
                raise CheckFailure(f"Internal {name} readiness timed out ({last})")


def flock_checks(request, sessions, *, broker, enrollment_token, internal_token, admin_token, verify=check):
    """Shared HTTP checks against a synthetic identity with no agent process.

    Every command string is an inert test sentinel, and each policy request must
    fail before insertion. The actual Docker heartbeat agent starts only later.
    """
    from app.models import FlockAgent, FlockEnrollmentToken, FlockTask, Node

    enrollment = {"name": "synthetic-smoke-agent", "hostname": "127.0.0.1", "metadata_json": {"environment": "disposable-smoke"}}
    for bad_token in ("invalid-test-token", "dev-flock-enrollment-token"):
        request("POST", "/api/flock/enroll", 401, base=broker, json={**enrollment, "enrollment_token": bad_token})
    payload = {**enrollment, "enrollment_token": enrollment_token}
    enrolled = request("POST", "/api/flock/enroll", base=broker, json=payload).json()
    agent_id, agent_token = enrolled["agent_id"], enrolled["agent_token"]
    policy_id = enrolled["policy"]["id"]
    with sessions() as db:
        disable_checks(db)

    def snapshot():
        with sessions() as db:
            return tuple(
                [tuple(getattr(row, column.key) for column in model.__table__.columns) for row in db.query(model).order_by(model.id)]
                for model in (FlockAgent, Node, FlockEnrollmentToken)
            )

    before = snapshot()
    for duplicate in (
        {**payload, "name": " SYNTHETIC-SMOKE-AGENT ", "hostname": "unused-smoke.invalid"},
        {**payload, "name": "unused-smoke-name", "hostname": " 127.0.0.1 "},
    ):
        request("POST", "/api/flock/enroll", 409, base=broker, json=duplicate)
        verify(snapshot() == before, "Rejected duplicate enrollment mutated an existing identity or inventory")
    rejoin = {**payload, "existing_agent_id": agent_id, "metadata_json": {"unexpected_replacement": True}}
    for token in (None, "invalid-agent-test-token"):
        request("POST", "/api/flock/enroll", 401, base=broker, token=token, json=rejoin)
        verify(snapshot() == before, "Rejected rejoin mutated an existing identity or inventory")
    rejoined = request("POST", "/api/flock/enroll", base=broker, token=agent_token, json=rejoin).json()
    verify(rejoined["agent_id"] == agent_id and rejoined["agent_token"] == agent_token, "Authenticated rejoin rotated an existing identity or token")
    verify(snapshot() == before, "Authenticated rejoin must retain original identity, metadata and inventory")

    agent_path = f"/api/flock/agents/{agent_id}"
    request("POST", agent_path + "/heartbeat", 401, base=broker, json={})
    request("POST", agent_path + "/heartbeat", 409, base=broker, token=agent_token, json={"hostname": "replacement-smoke.invalid"})
    request("POST", agent_path + "/heartbeat", base=broker, token=agent_token, json={"metrics_json": {"synthetic_smoke": True}})
    verify(request("POST", agent_path + "/tasks/claim", base=broker, token=agent_token).json() is None, "Unexpected agent command")
    agents = request("GET", "/api/flock/agents", token=admin_token).json()
    verify(len(agents) == 1 and agents[0]["agent_id"] == agent_id, "Broker/API inventory mismatch")
    database_agent_id = agents[0]["id"]
    request("GET", f"/api/flock/agents/{database_agent_id}/metrics", token=admin_token)
    dispatch_path = "/api/flock/internal/dispatch"
    headers = {"X-Flock-Internal-Token": internal_token}
    missing = {"target": "flock:nonexistent-disposable-agent", "command": "NOT_EXECUTED"}
    request("POST", dispatch_path, 401, base=broker, json=missing)
    request("POST", dispatch_path, 401, base=broker, headers={"X-Flock-Internal-Token": "dev-flock-internal-token"}, json=missing)
    result = request("POST", dispatch_path, base=broker, headers=headers, json=missing).json()
    verify(result["status"] == "failed" and result.get("task_id") is None, "Missing target must not create a task")

    def denied(command):
        result = request("POST", dispatch_path, base=broker, headers=headers, json={"target": f"flock:{agent_id}", "command": command, "timeout_seconds": 1}).json()
        verify(result["status"] == "failed" and result["exit_code"] == 126 and result.get("task_id") is None, "Policy denial must not create or dispatch a task")
        with sessions() as db:
            verify(db.query(FlockTask).count() == 0, "Policy denial queued unexpected work")

    policy_path = f"/api/flock/policies/{policy_id}"
    # These paths deliberately do not identify any actual executable.
    sentinel = "/raven-smoke-nonexistent-sentinel"
    request("PUT", policy_path, token=admin_token, json={"command_allowlist": [], "is_enabled": True})
    denied(sentinel)
    request("PUT", policy_path, token=admin_token, json={"command_allowlist": [sentinel + "-allowed"]})
    denied(sentinel)
    request("PUT", policy_path, token=admin_token, json={"is_enabled": False})
    denied(sentinel + "-allowed")
    request("PUT", f"/api/flock/agents/{database_agent_id}", token=admin_token, json={"policy_id": None})
    denied(sentinel)
    request("PUT", f"/api/flock/agents/{database_agent_id}", token=admin_token, json={"policy_id": policy_id})
    request("PUT", policy_path, token=admin_token, json={"command_allowlist": [], "is_enabled": True})
    verify(request("POST", agent_path + "/tasks/claim", base=broker, token=agent_token).json() is None, "Policy checks must leave the queue empty")
    print("PASS: duplicate enrollment/rejoin identity protection and empty/mismatched/disabled/missing policy denial; zero commands queued", flush=True)


def http_checks():
    settings, passwords = settings_and_passwords()
    import httpx
    from app.database import SessionLocal
    api, broker, frontend = "http://backend:8000", "http://flock:8000", "http://frontend:3000"
    origin = "http://127.0.0.1:3000"
    assertions = 0
    with httpx.Client(trust_env=False, timeout=15) as client:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if client.get(broker + "/api/health", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.5)
        else:
            raise CheckFailure("Internal broker readiness timed out")

        def request(method, path, status=200, *, base=api, token=None, **kwargs):
            nonlocal assertions
            headers = dict(kwargs.pop("headers", {}))
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = client.request(method, base + path, headers=headers, **kwargs)
            check(response.status_code == status, f"{method} {path}: expected {status}, got {response.status_code}")
            assertions += 1
            return response

        for base in (api, broker):
            for path in ("/", "/health", "/api/health"):
                request("GET", path, base=base)
        for path in ("/api/auth/me", "/api/nodes"):
            request("GET", path, 401)
        request("GET", "/api/auth/me", 401, token="invalid-disposable-test-token")
        request("POST", "/api/auth/login", 401, json={"username": "missing-test-user", "password": "invalid-test-password"})
        request("POST", "/api/auth/login", 422, json={})
        tokens = {}
        reads = ("/nodes", "/node-groups", "/dashboard/metrics", "/incidents", "/messages", "/messages?archived=true", "/profiles", "/audit/logs", "/validations", "/remediations", "/settings")
        for role, password in passwords.items():
            request("POST", "/api/auth/login", 401, json={"username": role, "password": role + "123!"})
            payload = request("POST", "/api/auth/login", json={"username": role, "password": password}).json()
            tokens[role] = token = payload["access_token"]
            check(payload["user"]["role"] == role, "Login role mismatch")
            me = request("GET", "/api/auth/me", token=token).json()
            check(me["username"] == role and "hashed_password" not in me, "Invalid user serialization")
            for path in reads:
                request("GET", "/api" + path, token=token)
            for path in ("/credentials", "/flock/agents", "/flock/policies"):
                request("GET", "/api" + path, 200 if role == "admin" else 403, token=token)
            # Nonexistent incident: dependency checks, not an executable action.
            request("POST", "/api/incidents/999999/acknowledge", 403 if role == "viewer" else 404, token=token)
            if role != "admin":
                request("PUT", "/api/settings", 403, token=token, json={})
                request("POST", "/api/node-groups", 403, token=token, json={"name": "docker-smoke-group"})
        admin = tokens["admin"]
        group = request("POST", "/api/node-groups", 201, token=admin, json={"name": "docker-smoke-group"}).json()
        request("DELETE", f"/api/node-groups/{group['id']}", 204, token=admin)
        cors = request("OPTIONS", "/api/auth/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        check(cors.headers.get("access-control-allow-origin") == origin, "CORS origin mismatch")
        request("OPTIONS", "/api/auth/login", 400, headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"})
        request("GET", "/api/dashboard/metrics?range=invalid", 422, token=admin)

        flock_checks(request, SessionLocal, broker=broker, enrollment_token=settings.flock_enrollment_token, internal_token=settings.flock_internal_token, admin_token=admin)

        for path in ("/", "/login", "/messages", "/infrastructure", "/alerts", "/reports", "/settings", "/credentials", "/validations", "/remediations"):
            response = request("GET", path, base=frontend)
            check("text/html" in response.headers.get("content-type", ""), "Frontend route did not return HTML")
            if path == "/login":
                check(not any(password in response.text for password in ("admin123!", "operator123!", "viewer123!")), "Login page must not expose demo credentials")
                check('autocomplete="username"' in response.text.lower() and 'autocomplete="current-password"' in response.text.lower(), "Login must support provisioned accounts and password managers")
        image = request("GET", "/_next/image?url=%2Fbrand%2Fraven-square-logo.png&w=96&q=75", base=frontend)
        check(image.headers.get("content-type", "").startswith("image/") and len(image.content) > 0, "Image optimizer failed")
    print(f"PASS: {assertions} container HTTP assertions: health/auth/roles/CORS/Flock/10 UI routes/image optimizer")
    audit()


def audit():
    settings_and_passwords()
    from app.database import SessionLocal
    from app.models import ExecutionTask, FlockTask, HealthCheckResult
    with SessionLocal() as db:
        check(db.query(ExecutionTask).count() == 0, "Unexpected execution task")
        check(db.query(FlockTask).count() == 0, "Unexpected Flock task")
        check(db.query(HealthCheckResult).count() == 0, "Monitoring unexpectedly executed")
        disable_checks(db)
    print("PASS: zero execution tasks, Flock commands, or health-check executions")


def wait_agent():
    settings_and_passwords()
    from app.database import SessionLocal
    from app.models import FlockAgent, FlockMetric
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            agent = db.query(FlockAgent).filter_by(name="disposable-docker-agent").first()
            if agent:
                metrics = db.query(FlockMetric).filter_by(agent_id=agent.id).all()
                disable_checks(db)
                # Two real heartbeat cycles, not just process existence/enrollment.
                if len(metrics) >= 2:
                    check(agent.status == "online", "Disposable agent is not online")
                    check(all(key in metrics[-1].payload_json for key in ("memory", "disk", "network")), "Agent metric payload incomplete")
                    print("PASS: real container agent enrolled and sent two metric heartbeats; no command dispatched")
                    audit()
                    return
        time.sleep(0.5)
    raise CheckFailure("Disposable agent heartbeat readiness timed out")


if __name__ == "__main__":
    try:
        {"seed": seed, "ready": ready, "http": http_checks, "audit": audit, "agent": wait_agent}[sys.argv[1]]()
    except Exception as exc:
        # Never dump arbitrary exception/request/response text containing credentials.
        detail = str(exc) if isinstance(exc, CheckFailure) else f"{type(exc).__name__}; private details suppressed"
        print(f"FAIL: container check {sys.argv[1] if len(sys.argv) > 1 else 'missing'}: {detail}", file=sys.stderr)
        raise SystemExit(1)
