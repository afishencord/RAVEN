#!/usr/bin/env python3
"""Run an isolated, loopback-only host deployment; never launch a runner/agent."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
BROKER = "http://127.0.0.1:8001"
FRONTEND = "http://127.0.0.1:3000"


def check(condition: bool, description: str) -> None:
    if not condition:
        raise RuntimeError(description)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", action="store_true", help="Keep services alive after checks until Enter/Ctrl-C, for manual browser inspection.")
    args = parser.parse_args()
    os.umask(0o077)
    check((ROOT / "frontend/.next/BUILD_ID").is_file(), "Build the frontend first; see LOCAL_VERIFICATION.md")
    chunks = (ROOT / "frontend/.next/static/chunks").rglob("*.js")
    check(any(f"{API}/api" in path.read_text() for path in chunks), "Frontend must be built with NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api")
    for port in (8000, 8001, 3000):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Fail rather than test or stop someone else's service.

    processes: list[subprocess.Popen] = []
    logs = []
    with tempfile.TemporaryDirectory(prefix="raven-local-smoke-") as work:
        passwords = {role: secrets.token_urlsafe(32) for role in ("admin", "operator", "viewer")}
        settings = {
            "DATABASE_URL": f"sqlite:///{work}/raven.db",
            "JWT_SECRET_KEY": secrets.token_urlsafe(48),
            "JWT_ALGORITHM": "HS256",
            "API_PREFIX": "/api",
            "FLOCK_INTERNAL_TOKEN": secrets.token_urlsafe(32),
            "FLOCK_ENROLLMENT_TOKEN": secrets.token_urlsafe(32),
            "FLOCK_SERVER_URL": f"{BROKER}/api/flock",
            "FRONTEND_ORIGIN": FRONTEND,
            "EMBEDDED_MONITORING": "false",
            "OPENAI_API_KEY": "",
            "NEXT_PUBLIC_API_BASE_URL": f"{API}/api",
            "NEXT_TELEMETRY_DISABLED": "1",
            "DEBUG": "false",
        }
        os.environ.update(settings)
        sys.path.insert(0, str(ROOT / "backend"))
        # Imports intentionally follow environment setup so no existing DB/config is used.
        import httpx
        from app.auth import get_password_hash
        from app.config import get_settings
        from app.database import Base, SessionLocal, engine, migrate_sqlite_schema
        from app.models import Credential, ExecutionTask, FlockTask, HealthCheckResult, Node, NodeHealthCheck, User
        from app.seed import seed_data

        check(not get_settings().embedded_monitoring, "Monitoring must be disabled")
        check(not get_settings().openai_api_key, "Live AI must be disabled")
        Base.metadata.create_all(bind=engine)
        migrate_sqlite_schema()
        with SessionLocal() as db:
            # Preseed random credentials, so demo passwords never exist in this database.
            for role, password in passwords.items():
                db.add(User(username=role, full_name=f"Local smoke {role}", role=role, hashed_password=get_password_hash(password)))
            db.commit()
            seed_data(db)
            db.query(Node).update({Node.is_enabled: False})
            db.query(NodeHealthCheck).update({NodeHealthCheck.is_enabled: False})
            for credential in db.query(Credential):
                credential.secret_value = secrets.token_urlsafe(32)
            db.commit()

        def start(name: str, command: list[str], cwd: Path) -> subprocess.Popen:
            log = open(Path(work) / f"{name}.log", "w+")
            logs.append(log)
            proc = subprocess.Popen(command, cwd=cwd, env=os.environ.copy(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(proc)
            print(f"Started {name}: pid={proc.pid}", flush=True)
            return proc

        def wait_ready(url: str, proc: subprocess.Popen) -> None:
            deadline = time.monotonic() + 60
            with httpx.Client(trust_env=False, timeout=1) as client:
                while time.monotonic() < deadline:
                    check(proc.poll() is None, f"Service exited before readiness: {url}")
                    try:
                        if client.get(url).status_code == 200:
                            return
                    except httpx.TransportError:
                        pass
                    time.sleep(0.2)
            raise RuntimeError(f"Service readiness timed out: {url}")

        checks = 0
        try:
            for name, module, port in (("backend", "app.main:app", "8000"), ("broker", "app.main_flock:app", "8001")):
                proc = start(name, [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", port, "--no-access-log"], ROOT / "backend")
                wait_ready(f"http://127.0.0.1:{port}/api/health", proc)
            frontend = start("frontend", ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3000"], ROOT / "frontend")
            wait_ready(f"{FRONTEND}/login", frontend)
            print(f"Loopback services: API={API}, broker={BROKER}, UI={FRONTEND}", flush=True)

            with httpx.Client(trust_env=False, timeout=10) as client:
                def request(method: str, path: str, status: int = 200, *, base: str = API, token: str | None = None, **kwargs):
                    nonlocal checks
                    headers = dict(kwargs.pop("headers", {}))
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                    response = client.request(method, f"{base}{path}", headers=headers, **kwargs)
                    check(response.status_code == status, f"{method} {path}: expected {status}, got {response.status_code}")
                    checks += 1
                    return response

                for base in (API, BROKER):
                    for path in ("/", "/health", "/api/health"):
                        request("GET", path, base=base)
                request("GET", "/api/auth/me", 401)
                request("GET", "/api/nodes", 401)
                request("GET", "/api/auth/me", 401, token="invalid-local-test-token")
                request("POST", "/api/auth/login", 401, json={"username": "missing-local-user", "password": secrets.token_urlsafe(32)})
                request("POST", "/api/auth/login", 422, json={})
                tokens = {}
                read_paths = ["/nodes", "/node-groups", "/dashboard/metrics", "/incidents", "/messages", "/messages?archived=true", "/profiles", "/audit/logs", "/validations", "/remediations", "/settings"]
                for role, password in passwords.items():
                    request("POST", "/api/auth/login", 401, json={"username": role, "password": role + "123!"})
                    payload = request("POST", "/api/auth/login", json={"username": role, "password": password}).json()
                    tokens[role] = token = payload["access_token"]
                    check(payload["user"]["role"] == role, "Login role mismatch")
                    me = request("GET", "/api/auth/me", token=token).json()
                    check(me["username"] == role and "hashed_password" not in me, "Invalid user serialization")
                    for path in read_paths:
                        request("GET", f"/api{path}", token=token)
                    for path in ("/credentials", "/flock/agents", "/flock/policies"):
                        request("GET", f"/api{path}", 200 if role == "admin" else 403, token=token)
                    # Nonexistent incident exercises operator dependency without any action/AI/command.
                    request("POST", "/api/incidents/999999/acknowledge", 403 if role == "viewer" else 404, token=token)
                    if role != "admin":
                        request("PUT", "/api/settings", 403, token=token, json={})
                        request("POST", "/api/node-groups", 403, token=token, json={"name": "local-smoke-group"})
                admin = tokens["admin"]
                group = request("POST", "/api/node-groups", 201, token=admin, json={"name": "local-smoke-group"}).json()
                request("DELETE", f"/api/node-groups/{group['id']}", 204, token=admin)
                cors = request("OPTIONS", "/api/auth/login", headers={"Origin": FRONTEND, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
                check(cors.headers.get("access-control-allow-origin") == FRONTEND, "CORS origin mismatch")
                request("GET", "/api/dashboard/metrics?range=invalid", 422, token=admin)
                print("PASS: health, all three roles, valid/invalid login, demo password rejection, authorization, reads, CORS, safe group CRUD", flush=True)

                enrollment = {"name": "local-smoke-agent", "hostname": "127.0.0.1", "metadata_json": {"environment": "isolated-local-test"}}
                request("POST", "/api/flock/enroll", 401, base=BROKER, json={**enrollment, "enrollment_token": "invalid-test-token"})
                enrolled = request("POST", "/api/flock/enroll", base=BROKER, json={**enrollment, "enrollment_token": settings["FLOCK_ENROLLMENT_TOKEN"]}).json()
                agent_id, agent_token = enrolled["agent_id"], enrolled["agent_token"]
                with SessionLocal() as db:
                    db.query(Node).update({Node.is_enabled: False})
                    db.query(NodeHealthCheck).update({NodeHealthCheck.is_enabled: False})
                    db.commit()
                agent_path = f"/api/flock/agents/{agent_id}"
                request("POST", f"{agent_path}/heartbeat", 401, base=BROKER, json={})
                request("POST", f"{agent_path}/heartbeat", base=BROKER, token=agent_token, json={"metrics_json": {"local_smoke": True}})
                check(request("POST", f"{agent_path}/tasks/claim", base=BROKER, token=agent_token).json() is None, "Unexpected queued agent command")
                agents = request("GET", "/api/flock/agents", token=admin).json()
                check(len(agents) == 1 and agents[0]["agent_id"] == agent_id, "Broker inventory not visible to API")
                request("GET", f"/api/flock/agents/{agents[0]['id']}/metrics", token=admin)
                dispatch = {"target": "flock:nonexistent-local-test-agent", "command": "NOT_EXECUTED"}
                request("POST", "/api/flock/internal/dispatch", 401, base=BROKER, json=dispatch)
                no_target = request("POST", "/api/flock/internal/dispatch", base=BROKER, headers={"X-Flock-Internal-Token": settings["FLOCK_INTERNAL_TOKEN"]}, json=dispatch).json()
                check(no_target["status"] == "failed", "Missing broker target should fail without queueing work")
                print("PASS: isolated Flock enrollment, authentication, synthetic heartbeat/metrics, inventory, empty task claim, internal-token guard; no agent executed", flush=True)

                for path in ("/", "/login", "/messages", "/infrastructure", "/alerts", "/reports", "/settings", "/credentials", "/validations", "/remediations"):
                    html = request("GET", path, base=FRONTEND)
                    check("text/html" in html.headers.get("content-type", ""), f"Frontend route is not HTML: {path}")
                image = request("GET", "/_next/image?url=%2Fbrand%2Fraven-square-logo.png&w=96&q=75", base=FRONTEND)
                check(image.headers.get("content-type", "").startswith("image/"), "Image optimizer response missing")
                print("PASS: 10 frontend HTTP routes and live Next image optimizer", flush=True)

            with SessionLocal() as db:
                check(db.query(ExecutionTask).count() == 0, "Unexpected execution task")
                check(db.query(FlockTask).count() == 0, "Unexpected Flock command task")
                check(db.query(HealthCheckResult).count() == 0, "Monitoring unexpectedly ran")
            print(f"PASS: {checks} HTTP assertions; no command tasks or health checks executed", flush=True)
            if args.hold:
                print("Services held for manual browser inspection; secrets remain private. Press Enter or Ctrl-C to stop.", flush=True)
                input()
        finally:
            for proc in reversed(processes):
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for proc in reversed(processes):
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=5)
            engine.dispose()
            for log in logs:
                log.close()
            print("Stopped all smoke-test services; removed temporary database and logs.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        # Do not dump request bodies, credentials, or child-process logs.
        print(f"Local smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
