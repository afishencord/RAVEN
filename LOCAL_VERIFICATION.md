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
- Requires a clean checkout without a root `.env` or frontend `.env*` files. Clears inherited application, proxy, SSH and interpreter-hook environment settings. Creates a private temporary directory and SQLite database; existing application data is never used or modified.
- Generates fresh JWT/Flock secrets and random passwords. Exercises the real secure `seed_data` bootstrap against an empty database, asserting that only the configured administrator exists and no demo infrastructure credential is created. Adds operator/viewer fixtures **before opening any listener**. Secrets are neither printed nor written to repository files.
- Sets `EMBEDDED_MONITORING=false` and clears `OPENAI_API_KEY`; disables test nodes/checks. Does not launch the runner or a Flock agent, invoke SSH, probe external nodes, request AI output, or dispatch an executable command.
- Exercises Flock with synthetic enrollment/heartbeat data and an empty task queue. Duplicate normalized name/hostname enrollment and unauthenticated rejoin must leave identity/token/metadata/inventory unchanged; authenticated rejoin must preserve them. Denies hostname replacement and empty, mismatched, disabled or missing command policies through HTTP, checking after each denial that no task exists. Command strings are nonexistent sentinel paths, never dispatched to a real agent.
- Stops its own child process groups and deletes the temporary database/logs on success, error, or Ctrl-C. Do not kill it with SIGKILL if graceful cleanup is required.

To inspect the UI before cleanup:

```bash
backend/.venv/bin/python scripts/local_smoke.py --hold
# Open http://127.0.0.1:3000/login; press Enter in the script terminal to stop.
```

The hold mode intentionally does not reveal generated passwords. Use it for anonymous UI/rendering and failed demo-login checks; authenticated role flows are already exercised by the script. The login screen no longer advertises demo credentials; shared deployments require their own secure bootstrap.

## What passes are required

The script verifies health endpoints; valid and invalid login; rejection of demo passwords; authenticated reads for admin/operator/viewer; missing/invalid bearer-token rejection; role restrictions; safe local node-group create/delete; CORS; Flock enrollment/authentication/rejoin protection/command-policy denials/heartbeat/shared inventory; ten frontend HTML routes; and the actual Next.js image-optimization endpoint. It checks that neither command tasks nor health checks ran.

Also run the repository checks against the final application changes:

```bash
python3 -m unittest discover -s scripts/tests -v
(cd backend && .venv/bin/python -m unittest discover -s tests -v)
(cd frontend && npm run typecheck && npm test)
```

The existing `npm run lint` command has no configured ESLint policy and may prompt for setup; it is not a passing automated check in this patch.

A passing HTTP smoke does not prove authenticated browser interactions, production configuration, Docker image builds, real AI requests, network monitoring, SSH, or command execution. Those must be reported separately, not inferred from this run.
