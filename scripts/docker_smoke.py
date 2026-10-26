#!/usr/bin/env python3
"""Build the real Dockerfiles and verify a disposable, isolated Compose deployment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("backend", "runner", "flock", "flock-test", "frontend")
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]


class SmokeFailure(RuntimeError):
    pass


def check(value, message):
    if not value:
        raise SmokeFailure(message)


def clean_env():
    # Never inherit COMPOSE_*, Docker contexts, app secrets, proxy variables, or
    # deployment .env files. Use only the local Linux Docker daemon.
    return {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TERM") if key in os.environ} | {"COMPOSE_ANSI": "never", "DOCKER_BUILDKIT": "1"}


def execute(command, phase, *, timeout=180, allow_failure=False, build_redactions=None, check_diagnostics=False):
    try:
        result = subprocess.run(command, cwd=ROOT, env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeFailure(f"{phase}: {type(exc).__name__}; no process output disclosed") from None
    if result.returncode and build_redactions is not None:
        # Only the build gets diagnostics: runtime/config/test output may contain
        # tokens. No secret is a Docker build arg or part of either build context.
        output = result.stdout
        for value in build_redactions:
            output = output.replace(value, "[REDACTED]")
        for line in output.splitlines()[-30:]:
            safe = "".join(char for char in line if char.isprintable())[:500]
            print("build | " + safe, file=sys.stderr, flush=True)
    if result.returncode and check_diagnostics:
        for line in result.stdout.splitlines():
            if line.startswith("FAIL: container check "):
                print(line, file=sys.stderr, flush=True)
    if not allow_failure:
        check(result.returncode == 0, f"{phase}: command exited {result.returncode}; private output withheld")
    return result


def compose(state):
    meta = json.loads((state / "state.json").read_text())
    check(re.fullmatch(r"raven-smoke-[a-f0-9]{16}", meta.get("project", "")), "Invalid cleanup project marker")
    return DOCKER + ["compose", "--project-directory", str(ROOT), "--project-name", meta["project"], "--env-file", str(state / "test.env"), "-f", str(ROOT / "docker-compose.yml"), "-f", str(state / "override.yml")]


def render_override(state, project):
    # Explicit !override prevents Compose's port/volume/env list merge from
    # accidentally retaining 0.0.0.0 listeners or the original .env/dev tokens.
    lines = ["services:"]
    for service in SERVICES:
        lines += [f"  {service}:", "    container_name: !reset null", '    restart: "no"', '    logging: {driver: "none"}', "    security_opt: [no-new-privileges:true]", "    cap_drop: [ALL]", "    networks: !override [default]"]
        if service == "frontend":
            lines += ["    env_file: !override []", "    environment: !override", "      NEXT_PUBLIC_API_BASE_URL: http://127.0.0.1:8000/api", '      NEXT_TELEMETRY_DISABLED: "1"', "    build:", "      args:", "        NEXT_PUBLIC_API_BASE_URL: http://127.0.0.1:8000/api", '    ports: !override ["127.0.0.1:3000:3000"]']
        else:
            lines += [f"    env_file: !override [{json.dumps(str(state / 'test.env'))}]"]
            if service != "backend":
                lines += ["    ports: !override []"]
            if service != "flock-test":
                lines += ["    environment: !override {}"]
        if service == "backend":
            lines += ['    ports: !override ["127.0.0.1:8000:8000"]', '    command: [uvicorn, "app.main:app", --host, "0.0.0.0", --port, "8000", --no-access-log]', "    volumes: !override", "      - raven-data:/data", f"      - {json.dumps(str(ROOT / 'scripts/container_checks.py') + ':/checks/container_checks.py:ro')}", f"      - {json.dumps(str(state / 'passwords.json') + ':/checks/passwords.json:ro')}", f"      - {json.dumps(str(ROOT / 'backend/tests') + ':/app/tests:ro')}"]
        elif service == "flock":
            lines += ['    command: [uvicorn, "app.main_flock:app", --host, "0.0.0.0", --port, "8000", --no-access-log]']
        elif service == "flock-test":
            lines += ["    environment: !override", "      FLOCK_AGENT_NAME: disposable-docker-agent", "      FLOCK_AGENT_STATE_PATH: /agent-state/flock-agent-state.json"]
    lines += ["networks:", "  default:", "    internal: true", "volumes:", "  raven-data:", f"    name: {project}-data", "  flock-test-state:", f"    name: {project}-agent-state"]
    return "\n".join(lines) + "\n"


def validate_config(model, state):
    check(set(model["services"]) == set(SERVICES), "Unexpected Compose service")
    check(model["networks"]["default"].get("internal") is True, "Runtime network must be internal")
    for name, service in model["services"].items():
        check(not service.get("container_name"), "Hardcoded container name survived override")
        check(service.get("restart") == "no", "Unexpected service restart policy")
        check(service.get("logging", {}).get("driver") == "none", "Container logging must be disabled")
        ports = service.get("ports", [])
        expected = {"backend": [(8000, "8000")], "frontend": [(3000, "3000")]}.get(name, [])
        check([(port["target"], str(port["published"])) for port in ports] == expected, "Unexpected published ports")
        check(all(port.get("host_ip") == "127.0.0.1" for port in ports), "Non-loopback listener")
        check(set(service.get("networks", {})) == {"default"}, "Unexpected runtime network")
        env = service.get("environment", {})
        if name != "frontend":
            check(env.get("EMBEDDED_MONITORING") == "false" and env.get("OPENAI_API_KEY") == "", "Monitoring/AI must be disabled")
            check(env.get("DATABASE_URL") == "sqlite:////data/raven.db", "Unexpected database URL")
            for key in ("JWT_SECRET_KEY", "FLOCK_INTERNAL_TOKEN", "FLOCK_ENROLLMENT_TOKEN"):
                check(len(env.get(key, "")) >= 40 and not env[key].startswith("dev-"), "Fresh secrets missing")
        for mount in service.get("volumes", []):
            if mount["type"] == "bind":
                check(mount.get("read_only") is True, "Test inputs must be read-only")
                check(mount["source"] in {str(state / "passwords.json"), str(ROOT / "scripts/container_checks.py"), str(ROOT / "backend/tests")}, "Unexpected bind mount")
        check(service.get("build", {}).get("context") == str(ROOT / ("frontend" if name == "frontend" else "backend")), "Unexpected Docker build context")
    check(model["services"]["frontend"]["build"]["args"]["NEXT_PUBLIC_API_BASE_URL"] == "http://127.0.0.1:8000/api", "Frontend build URL must be loopback")


def prepare(state):
    state.mkdir(mode=0o700)  # Refuse existing directories; never overwrite user data.
    try:
        project = "raven-smoke-" + secrets.token_hex(8)
        (state / "state.json").write_text(json.dumps({"project": project}))
        values = {"RAVEN_DISPOSABLE_SMOKE": "1", "DATABASE_URL": "sqlite:////data/raven.db", "JWT_SECRET_KEY": secrets.token_urlsafe(48), "JWT_ALGORITHM": "HS256", "FLOCK_INTERNAL_TOKEN": secrets.token_urlsafe(48), "FLOCK_ENROLLMENT_TOKEN": secrets.token_urlsafe(48), "FLOCK_SERVER_URL": "http://flock:8000/api/flock", "FRONTEND_ORIGIN": "http://127.0.0.1:3000", "EMBEDDED_MONITORING": "false", "OPENAI_API_KEY": "", "DEBUG": "false", "RUNNER_POLL_SECONDS": "1"}
        (state / "test.env").write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        (state / "passwords.json").write_text(json.dumps({role: secrets.token_urlsafe(48) for role in ("admin", "operator", "viewer")}))
        # The enclosing host directory stays 0700. The read-only individual bind
        # must be readable by container root after dropping DAC_OVERRIDE.
        (state / "passwords.json").chmod(0o444)
        (state / "override.yml").write_text(render_override(state, project))
    except BaseException:
        # No container is created until preparation and validation both finish.
        shutil.rmtree(state)
        raise


def cleanup(state):
    if not state.exists():
        return
    check((state / "state.json").is_file(), "Refusing cleanup without disposable project marker")
    command = compose(state)
    result = execute(command + ["down", "--volumes", "--remove-orphans", "--rmi", "local", "--timeout", "10"], "cleanup", timeout=120, allow_failure=True)
    check(result.returncode == 0, "Docker cleanup failed; keep private state for --cleanup retry")
    project = json.loads((state / "state.json").read_text())["project"]
    for kind, args in (("containers", ["ps", "-aq"]), ("volumes", ["volume", "ls", "-q"]), ("networks", ["network", "ls", "-q"])):
        remaining = execute(DOCKER + args + ["--filter", f"label=com.docker.compose.project={project}"], "cleanup verification").stdout.strip()
        check(not remaining, f"Disposable {kind} remain; keep private state for --cleanup retry")
    shutil.rmtree(state)
    print("PASS: disposable containers, volumes, network and private secret files removed", flush=True)


def wait_ready(url):
    # Do not honor proxy environment variables for loopback checks.
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with client.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    raise SmokeFailure("Loopback service readiness timed out")


def verify_running(command):
    for name in SERVICES:
        container = execute(command + ["ps", "-q", name], f"{name} container lookup").stdout.strip()
        check(bool(container), f"{name} container is missing")
        running = execute(DOCKER + ["inspect", "--format", "{{.State.Running}}:{{.State.Restarting}}:{{.RestartCount}}", container], f"{name} process state").stdout.strip()
        check(running == "true:false:0", f"{name} exited or restarted")
    print("PASS: all five Compose services running without restarts; runner observed idle", flush=True)


def run(state):
    check(shutil.which("docker"), "Docker CLI is unavailable; no Docker checks ran")
    check(Path("/var/run/docker.sock").exists(), "Local Linux Docker socket unavailable; no Docker checks ran")
    check(not any(path.is_file() and path.name.startswith(".env") for path in (ROOT / "frontend").iterdir()), "Remove frontend .env files from the build context; use a clean checkout")
    version = execute(DOCKER + ["compose", "version", "--short"], "Compose version").stdout.strip().lstrip("v")
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    check(match and tuple(map(int, match.groups())) >= (2, 24, 4), "Docker Compose >= 2.24.4 is required")
    for port in (8000, 3000):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    prepare(state)
    try:
        command = compose(state)
        model = json.loads(execute(command + ["config", "--format", "json"], "private Compose validation").stdout)
        validate_config(model, state)
        print("PASS: effective Compose configuration is loopback-only, internal-networked and disposable", flush=True)
        redactions = [value for service in model["services"].values() for value in service.get("environment", {}).values() if isinstance(value, str) and len(value) >= 40]
        redactions += list(json.loads((state / "passwords.json").read_text()).values())
        execute(command + ["build", "--pull"], "Docker image build", timeout=1200, build_redactions=redactions)
        print("PASS: actual backend and frontend Dockerfiles built", flush=True)
        backend_tests = execute(command + ["run", "--rm", "--no-deps", "-T", "backend", "python", "-m", "unittest", "discover", "-s", "tests", "-v"], "backend container unit tests", timeout=180)
        count = re.search(r"Ran (\d+) tests?", backend_tests.stdout)
        print(f"PASS: backend container unit suite ({count.group(1) if count else 'all'} tests)", flush=True)
        execute(command + ["run", "--rm", "--no-deps", "-T", "frontend", "sh", "-c", "npm run typecheck && npm test"], "frontend container typecheck/unit tests", timeout=180)
        print("PASS: frontend container typecheck, dependency/CSS/native Sharp unit tests", flush=True)
        execute(command + ["run", "--rm", "--no-deps", "-T", "backend", "python", "/checks/container_checks.py", "seed"], "pre-listener random account seeding", check_diagnostics=True)
        print("PASS: random users seeded before opening listeners", flush=True)
        execute(command + ["up", "--detach", "--no-build", "backend", "flock", "runner", "frontend"], "Compose deployment")
        wait_ready("http://127.0.0.1:8000/api/health")
        wait_ready("http://127.0.0.1:3000/login")
        print("PASS: published loopback API and frontend respond", flush=True)
        for phase in ("http",):
            result = execute(command + ["exec", "-T", "backend", "python", "/checks/container_checks.py", phase], "container HTTP smoke", check_diagnostics=True)
            for line in result.stdout.splitlines():
                if line.startswith("PASS:"):
                    print(line, flush=True)
        # Agent starts only after proving the queue is empty. The harness never
        # sends a command to an enrolled target; this is an idle heartbeat test.
        execute(command + ["up", "--detach", "--no-build", "--no-deps", "flock-test"], "disposable idle agent start")
        result = execute(command + ["exec", "-T", "backend", "python", "/checks/container_checks.py", "agent"], "real agent idle heartbeats", timeout=90, check_diagnostics=True)
        for line in result.stdout.splitlines():
            if line.startswith("PASS:"):
                print(line, flush=True)
        verify_running(command)
        # The frontend API address is build-time, not just a runtime environment.
        execute(command + ["exec", "-T", "frontend", "node", "-e", "const fs=require('fs'),p=require('path');function scan(d){return fs.readdirSync(d,{withFileTypes:true}).some(e=>e.isDirectory()?scan(p.join(d,e.name)):e.name.endsWith('.js')&&fs.readFileSync(p.join(d,e.name),'utf8').includes('http://127.0.0.1:8000/api'))}if(!scan('.next/static/chunks'))process.exit(1)"], "compiled frontend API URL")
        print("PASS: compiled browser API URL is loopback; browser interaction testing not performed", flush=True)
    finally:
        cleanup(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, help="New private temporary directory; never use an existing data directory")
    parser.add_argument("--cleanup", action="store_true", help="Retry cleanup for this harness's existing state directory")
    args = parser.parse_args()
    check(not args.cleanup or args.state_dir is not None, "--cleanup requires --state-dir")
    os.umask(0o077)
    state = args.state_dir.resolve() if args.state_dir else Path(tempfile.gettempdir()) / ("raven-docker-smoke-" + secrets.token_hex(8))
    if args.cleanup:
        cleanup(state)
    else:
        run(state)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        main()
    except KeyboardInterrupt:
        print("Docker smoke interrupted; cleanup attempted", file=sys.stderr)
        raise SystemExit(130)
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}; private details suppressed", file=sys.stderr)
        raise SystemExit(1)
