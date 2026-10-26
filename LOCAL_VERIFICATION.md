# Isolated local verification

This is a disposable **host-process** smoke deployment, not a production deployment or a substitute for a Docker image build. It requires Python 3.12, Node.js 24, and the backend/frontend dependencies. Run from the repository root.

```bash
# Use a Python 3.12 interpreter for the virtual environment.
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r backend/requirements.txt
(cd frontend && npm ci)
(cd frontend && NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api npm run build)
backend/.venv/bin/python scripts/local_smoke.py
```

`uv venv --python 3.12 backend/.venv` and `uv pip sync --require-hashes --no-build --python backend/.venv/bin/python backend/requirements.txt` are equivalent alternatives when `uv` is available.

The public API URL is compiled into the frontend bundle: setting it only when starting Next.js is not sufficient. Rebuild with the loopback URL shown above.

## Isolation and cleanup

- Binds only `127.0.0.1:8000` (API), `127.0.0.1:8001` (Flock broker), and `127.0.0.1:3000` (frontend). Occupied ports cause an error rather than replacing an existing service.
- Creates a private temporary directory and SQLite database. Existing application data and environment files are not modified.
- Generates fresh JWT/Flock secrets and random passwords for all three test roles. Users are created **before seeding or opening any listener**, so known demo passwords never work in this database. Secrets are neither printed nor written to repository files.
- Sets `EMBEDDED_MONITORING=false` and clears `OPENAI_API_KEY`; disables test nodes/checks. Does not launch the runner or a Flock agent, invoke SSH, probe external nodes, request AI output, or dispatch an executable command.
- Exercises Flock with synthetic enrollment/heartbeat data and an empty task queue. The dispatch test uses a nonexistent target and confirms no task is created.
- Stops its own child process groups and deletes the temporary database/logs on success, error, or Ctrl-C. Do not kill it with SIGKILL if graceful cleanup is required.

To inspect the UI before cleanup:

```bash
backend/.venv/bin/python scripts/local_smoke.py --hold
# Open http://127.0.0.1:3000/login; press Enter in the script terminal to stop.
```

The hold mode intentionally does not reveal generated passwords. Use it for anonymous UI/rendering and failed demo-login checks; authenticated role flows are already exercised by the script. Never use the visible demo credentials for a shared deployment.

## What passes are required

The script verifies health endpoints; valid and invalid login; rejection of demo passwords; authenticated reads for admin/operator/viewer; missing/invalid bearer-token rejection; role restrictions; safe local node-group create/delete; CORS; Flock enrollment/authentication/heartbeat/shared inventory; ten frontend HTML routes; and the actual Next.js image-optimization endpoint. It checks that neither command tasks nor health checks ran.

Also run the repository checks against the final dependency versions:

```bash
(cd backend && .venv/bin/python -m unittest discover -s tests -v)
(cd frontend && npm run typecheck && npm test)
```

The existing `npm run lint` command has no configured ESLint policy and may prompt for setup; it is not a passing automated check in this patch.

A passing HTTP smoke does not prove authenticated browser interactions, production configuration, Docker image builds, real AI requests, network monitoring, SSH, or command execution. Those must be reported separately, not inferred from this run.
