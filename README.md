# RAVEN

RAVEN is a semi-autonomous IT remediation dashboard for monitored application and infrastructure nodes. It records health checks, opens incidents when checks fail, generates AI-assisted remediation guidance, and routes approved commands through a separate runner process. The UI is designed as a production-style SaaS dashboard with a live, chat-like Message Center workflow.

## License

This project is source-available for demo and personal use only.

Enterprise use, production deployment, business integration, redistribution, rebranding, or commercial use requires a separate paid enterprise license.

See the [LICENSE](./LICENSE) file for full terms.

## Stack

- Frontend: Next.js App Router, React, Tailwind CSS
- Backend: FastAPI, SQLAlchemy, Pydantic
- Database: SQLite for the MVP, stored in a shared Docker volume
- AI: OpenAI Responses API via `OPENAI_API_KEY`
- Background work:
  - Embedded monitoring loop in the backend container
  - Separate runner container for approved command execution

## Project Structure

```text
backend/
  app/
    api/                  FastAPI routers
    services/             monitoring, incident workflow, AI, runner, health checks
    models.py             SQLAlchemy models
    schemas.py            Pydantic request/response schemas
    database.py           database setup and lightweight SQLite migrations
    seed.py               seeded users, nodes, profiles, and cleanup
    main.py               FastAPI entrypoint
frontend/
  app/                    Next.js routes
  components/             shared UI components
  lib/                    API client, shared types, live-refresh hook
  public/brand/           RAVEN brand images
docker-compose.yml        backend, runner, and frontend deployment
```

## Current Capabilities

- Full-screen enterprise dashboard with collapsible dark sidebar, light workspace, and dark mode
- JWT authentication with `viewer`, `operator`, and `admin` roles
- Analytics dashboard with node-state, remediation, execution, environment, approval, and failure visualizations
- Infrastructure workspace with tabbed Nodes and Fleet views
- Node CRUD, enable/disable, status filtering, drag-and-drop grouping, and live status updates
- Node detail view with live health check, incident, recommendation, and execution history
- Admin-only credential management with a full-width table layout
- Alerts page (work in progress, frontend wired) with a unified notification table and date/category filters
- Reports page (work in progress, frontend wired) with report previews and CSV/JSON export
- Settings page (work in progress, frontend wired) for model, API key override, LDAP/SSO, organization, notification, retention, and execution settings
- Message Center with:
  - live active and archived incident conversations
  - chat-style remediation timeline
  - minimized conversations by default, except the newest active incident
  - archive and restore support
  - operator notes
  - health re-checks
  - AI recommendation turns
  - human approve/reject flow for command cards
  - command output rendered inline in the thread
  - `Close incident` and `Investigate further` cards after healthy validation
- Iterative AI remediation:
  - initial recommendation is generated when an incident is created
  - follow-up recommendations use raw command output and health-check results as context
  - follow-up responses are intentionally short
  - each AI turn produces three command cards
  - new proposal IDs are generated to avoid repeating prior command cards
- Separate runner process for queued command execution
- Audit logs and approval decision records

## Security Model

RAVEN keeps AI out of the direct execution path:

- AI can propose command cards, but it cannot execute them.
- Operators/Admins must explicitly approve a command card.
- Approved commands are written to `execution_tasks`.
- The `raven-runner` container polls queued tasks and performs execution.
- Frontend code never executes shell commands.
- Command execution records include command preview, exit code, output, and post-action validation.
- OpenAI calls are limited to incident recommendation generation and user/operator-prompted follow-up workflows.

The runner currently treats exit codes `0` and `3` as successful command completions. Post-action validation still determines whether the incident appears resolved.

## Seeded Users

- `admin / admin123!`
- `operator / operator123!`
- `viewer / viewer123!`

Change these before any shared or persistent deployment.

## Environment

Create a local environment file:

```bash
cp .env.example .env
```

Important values:

- `OPENAI_API_KEY`: enables live AI recommendations. If unset, RAVEN uses deterministic fallback recommendations.
- `OPENAI_MODEL`: model used by the recommendation service.
- `FRONTEND_ORIGIN`: keep as `http://localhost:3000` for Docker Compose.

Docker Compose overrides `DATABASE_URL` to `sqlite:////data/raven.db` so backend and runner share state through the `raven-data` volume.

## Docker Compose Deployment

The intended local deployment path is Docker Compose.

```bash
docker compose up --build -d --remove-orphans
```

Services:

- `raven-backend`: FastAPI API plus embedded monitoring loop
- `raven-runner`: approved command execution daemon
- `raven-frontend`: Next.js UI

Open:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

Check status:

```bash
docker compose ps
docker compose exec -T backend curl -fsS http://localhost:8000/api/health
docker compose exec -T backend curl -fsSI http://frontend:3000/messages
```

Stop:

```bash
docker compose down
```

Remove persisted SQLite data too:

```bash
docker compose down -v
```

## Local Non-Docker Development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Runner in a second shell:

```bash
cd backend
source .venv/bin/activate
python -m app.services.execution_runner
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Validation Workflow

Recommended checks before considering changes complete:

```bash
cd frontend
npm exec tsc -- --noEmit --incremental false
npm run build
```

```bash
cd /path/to/RAVEN
python -m compileall backend/app
docker compose up --build -d --remove-orphans
docker compose ps
docker compose exec -T backend curl -fsS http://localhost:8000/api/health
docker compose exec -T backend curl -fsSI http://frontend:3000/messages
```

If `npm run build` fails in a sandbox with an `EPERM` copyfile error under `.next`, rerun outside the sandbox. The app can still compile successfully before that sandbox-specific copy step fails.

## API Highlights

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET|POST /api/nodes`
- `GET|PUT|DELETE /api/nodes/{id}`
- `GET /api/nodes/{id}/detail`
- `POST /api/nodes/{id}/rerun-check`
- `GET /api/node-groups`
- `POST /api/node-groups`
- `DELETE /api/node-groups/{id}`
- `GET /api/dashboard/metrics`
- `GET /api/audit/logs`
- `GET /api/audit/approvals`
- `GET /api/messages`
- `GET /api/messages?archived=true`
- `POST /api/incidents/{id}/acknowledge`
- `POST /api/incidents/{id}/archive`
- `POST /api/incidents/{id}/unarchive`
- `POST /api/incidents/{id}/close`
- `POST /api/incidents/{id}/investigate-further`
- `POST /api/incidents/{id}/notes`
- `POST /api/incidents/{id}/recommendation/refresh`
- `POST /api/incidents/{id}/approve`
- `POST /api/incidents/{id}/reject`
- `GET /api/profiles`
- `GET /api/credentials`

## Message Center Workflow

1. Monitoring detects repeated health-check failures.
2. Backend creates an incident and internal alert message.
3. AI generates the initial summary and three command cards using node context and failure details.
4. Operator approves or rejects one proposed command.
5. Runner executes approved commands and records output.
6. Backend performs post-action validation.
7. If validation is still unhealthy, AI generates a new short follow-up using raw command output.
8. If validation is healthy, UI shows:
   - `Close incident`: marks resolved and archives the conversation.
   - `Investigate further`: keeps the thread active and starts root-cause analysis.

Archived conversations remain available from the Archived tab.

## Execution Target Conventions

The runner supports transport-aware targets:

- `local:<subject>`
- `ssh:<host>:<subject>`
- `api:<endpoint>:<subject>`

Examples:

- `local:raven-backend`
- `ssh:ops@app01:raven-web.service`
- `api:https://runner.example.internal:raven-api`

The seeded MVP data uses `local:raven-backend`.

## Current Limitations

- SQLite is used for MVP simplicity. PostgreSQL is the likely production migration path.
- The monitoring loop currently runs inside the backend process.
- The runner executes commands available inside its own container or through SSH/API targets.
- Managing host Docker or host services from the runner requires explicit host integration.
- AI command proposals should still be reviewed carefully before approval.
