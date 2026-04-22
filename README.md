# RAVEN

RAVEN is an MVP semi-autonomous IT remediation platform for web application nodes. It monitors nodes, records health checks and incidents, generates AI-assisted remediation recommendations from an approved catalog, presents those recommendations in an internal message center, and queues only human-approved remediations for execution through a separate secure runner.

## Stack

- Frontend: Next.js App Router + Tailwind CSS
- Backend: FastAPI + SQLAlchemy
- Database: SQLite for MVP
- AI: OpenAI Responses API via `OPENAI_API_KEY`
- Background work:
  - Embedded monitoring loop inside the FastAPI app
  - Separate runner daemon for approved remediations

## Project structure

```text
backend/
  app/
    api/                  FastAPI routes
    services/             monitoring, AI, execution, health-check logic
    main.py               app entrypoint
frontend/
  app/                    Next.js pages
  components/             UI building blocks
  lib/                    API client and shared types
```

## MVP capabilities

- Dashboard for node CRUD, enable/disable, and status filtering
- Node detail page with:
  - health check history
  - incident history
  - AI recommendation history
  - execution history
  - assigned remediation profile
- Internal message center with:
  - acknowledge
  - add note
  - refresh recommendation
  - approve remediation
  - reject remediation
  - rerun health check
- Secure execution queue with allowlisted actions only
- Remediation profiles with cooldowns and approved targets
- JWT auth with `viewer`, `operator`, and `admin`
- Audit log and approval decision exposure

## Security model

The MVP intentionally keeps AI out of the execution path:

- The AI can only recommend `action_key` values from the predefined remediation catalog.
- The frontend never executes shell commands directly.
- Operators/Admins approve actions through the API.
- Approved actions are written to `execution_tasks`.
- A separate runner process polls the queue and executes only allowlisted actions tied to a remediation profile.
- Each execution is logged with command preview, exit code, output, and post-action validation.

`backend/app/services/remediation_catalog.py` is the main allowlist boundary. Keep new actions constrained and reviewable.

## Seeded credentials

- `admin / admin123!`
- `operator / operator123!`
- `viewer / viewer123!`

Change these before any shared or persistent deployment.

## Local setup

### 1. Configure environment

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` if you want live AI recommendations. Without it, RAVEN falls back to deterministic catalog-based recommendations so the workflow remains usable.

### 2. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

This starts:

- the FastAPI API on `http://localhost:8000`
- the embedded monitoring loop
- database creation and seed data on first boot

### 3. Start the secure runner

Run the runner in a second shell so approved executions can leave the queue:

```bash
cd backend
source .venv/bin/activate
python -m app.services.execution_runner
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Docker Compose

RAVEN can run as three containers:

- `backend`: FastAPI API plus embedded monitoring loop
- `runner`: secure execution runner polling approved remediation tasks
- `frontend`: Next.js UI
- `test`: simple `nginx` page for agent-response testing on port `6767`

The backend and runner share a named Docker volume for the SQLite database so they operate on the same state.

### 1. Configure environment

```bash
cp .env.example .env
```

For Docker Compose, keep `FRONTEND_ORIGIN=http://localhost:3000`. The compose file overrides `DATABASE_URL` to `sqlite:////data/raven.db` so the database lives in a shared container volume.

### 2. Start the stack

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Test page: `http://localhost:6767`

### 3. Stop the stack

```bash
docker compose down
```

To remove the persisted SQLite data volume too:

```bash
docker compose down -v
```

## API highlights

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET|POST /api/nodes`
- `GET|PUT|DELETE /api/nodes/{id}`
- `GET /api/nodes/{id}/detail`
- `POST /api/nodes/{id}/rerun-check`
- `GET /api/messages`
- `POST /api/incidents/{id}/acknowledge`
- `POST /api/incidents/{id}/notes`
- `POST /api/incidents/{id}/recommendation/refresh`
- `POST /api/incidents/{id}/approve`
- `POST /api/incidents/{id}/reject`
- `GET /api/profiles`
- `GET /api/audit/logs`
- `GET /api/audit/approvals`

## Example remediation profiles

- `webapp-basic`
- `api-basic`
- `host-basic`

These are seeded automatically and can be extended in `backend/app/seed.py`.

## Execution target conventions

The runner supports transport-aware targets:

- `local:<subject>`
- `ssh:<host>:<subject>`
- `api:<endpoint>:<subject>`

Examples:

- `local:raven-web.service`
- `ssh:ops@app01:raven-web.service`
- `api:https://runner.example.internal:raven-api`

For the seeded MVP data, targets use `local:*`.

## Notes for extending later

- Slack/webhook support can attach to the `alert_messages` model without changing incident creation.
- SQLite models were kept relational and portable for a PostgreSQL migration later.
- The runner abstraction already separates local, SSH, and API dispatch modes.

## Current limitations

- The monitoring loop is in-process for MVP simplicity. Production deployment should move it to a dedicated worker.
- The secure runner container can execute allowlisted commands available inside its own container, or call SSH/API targets. If you want it to manage host services or host Docker directly, that requires an explicit host-integration design beyond this MVP compose setup.
- The frontend is intentionally client-side heavy to keep the prototype fast to iterate on.
