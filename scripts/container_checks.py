#!/usr/bin/env python3
"""Private disposable-container checks; never dispatch a command to a real agent."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
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
        # This commits BEFORE seed_data or any listener can expose default users.
        for role, password in passwords.items():
            db.add(User(username=role, role=role, full_name=f"Disposable Docker {role}", hashed_password=get_password_hash(password)))
        db.commit()
        seed_data(db)
        disable_checks(db)
        for credential in db.query(Credential):
            credential.secret_value = secrets.token_urlsafe(48)
        for policy in db.query(FlockPolicy):
            policy.heartbeat_interval_seconds = 1
        db.commit()
        for user in db.query(User):
            check(not verify_password(user.username + "123!", user.hashed_password), "Demo password unexpectedly enabled")
    engine.dispose()
    print("PASS: random accounts preseeded before listeners; monitoring/AI disabled")


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

        enrollment = {"name": "synthetic-docker-smoke", "hostname": "127.0.0.1", "metadata_json": {"environment": "disposable-container"}}
        for bad_token in ("invalid-test-token", "dev-flock-enrollment-token"):
            request("POST", "/api/flock/enroll", 401, base=broker, json={**enrollment, "enrollment_token": bad_token})
        enrolled = request("POST", "/api/flock/enroll", base=broker, json={**enrollment, "enrollment_token": settings.flock_enrollment_token}).json()
        agent_id, agent_token = enrolled["agent_id"], enrolled["agent_token"]
        with SessionLocal() as db:
            disable_checks(db)
        agent_path = f"/api/flock/agents/{agent_id}"
        request("POST", agent_path + "/heartbeat", 401, base=broker, json={})
        request("POST", agent_path + "/heartbeat", base=broker, token=agent_token, json={"metrics_json": {"synthetic_smoke": True}})
        check(request("POST", agent_path + "/tasks/claim", base=broker, token=agent_token).json() is None, "Unexpected agent command")
        agents = request("GET", "/api/flock/agents", token=admin).json()
        check(len(agents) == 1 and agents[0]["agent_id"] == agent_id, "Broker/API inventory mismatch")
        request("GET", f"/api/flock/agents/{agents[0]['id']}/metrics", token=admin)
        # No target exists, therefore this cannot queue or dispatch executable work.
        dispatch = {"target": "flock:nonexistent-disposable-agent", "command": "NOT_EXECUTED"}
        request("POST", "/api/flock/internal/dispatch", 401, base=broker, json=dispatch)
        request("POST", "/api/flock/internal/dispatch", 401, base=broker, headers={"X-Flock-Internal-Token": "dev-flock-internal-token"}, json=dispatch)
        result = request("POST", "/api/flock/internal/dispatch", base=broker, headers={"X-Flock-Internal-Token": settings.flock_internal_token}, json=dispatch).json()
        check(result["status"] == "failed" and result.get("task_id") is None, "Missing target must not create a task")

        for path in ("/", "/login", "/messages", "/infrastructure", "/alerts", "/reports", "/settings", "/credentials", "/validations", "/remediations"):
            response = request("GET", path, base=frontend)
            check("text/html" in response.headers.get("content-type", ""), "Frontend route did not return HTML")
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
        {"seed": seed, "http": http_checks, "audit": audit, "agent": wait_agent}[sys.argv[1]]()
    except Exception as exc:
        # Never dump arbitrary exception/request/response text containing credentials.
        detail = str(exc) if isinstance(exc, CheckFailure) else f"{type(exc).__name__}; private details suppressed"
        print(f"FAIL: container check {sys.argv[1] if len(sys.argv) > 1 else 'missing'}: {detail}", file=sys.stderr)
        raise SystemExit(1)
