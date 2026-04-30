# RAVEN

RAVEN is a semi-autonomous IT remediation dashboard for monitored application and infrastructure nodes. It records health checks, opens incidents when checks fail, generates AI-assisted remediation guidance, and routes approved commands through runner or Flock agent execution paths. The UI is designed as a production-style SaaS dashboard with a live, chat-like Message Center workflow.

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
  - Flock server and Linux/Unix agent loop for node-local command execution

## Project Structure

```text
backend/
  app/
    api/                  FastAPI routers
    services/             monitoring, incident workflow, AI, runner, Flock, health checks
    models.py             SQLAlchemy models
    schemas.py            Pydantic request/response schemas
    database.py           database setup and lightweight SQLite migrations
    seed.py               seeded users, nodes, profiles, and cleanup
    main.py               FastAPI backend entrypoint
    main_flock.py         Flock server entrypoint
frontend/
  app/                    Next.js routes
  components/             shared UI components
  lib/                    API client, shared types, live-refresh hook
  public/brand/           RAVEN brand images
docker-compose.yml        backend, runner, Flock, test agent, and frontend deployment
```

## Current Capabilities

- Full-screen enterprise dashboard with collapsible dark sidebar, light workspace, and dark mode
- JWT authentication with `viewer`, `operator`, and `admin` roles
- Analytics dashboard with node-state, remediation, execution, environment, approval, and failure visualizations
- Infrastructure workspace with tabbed Nodes and Flock views
- Node CRUD, enable/disable, status filtering, drag-and-drop grouping, and live status updates
- Add/Edit Node execution setup with Runner and Agent tabs
- Flock tab for enrolled agents, heartbeat status, policy assignment, and policy controls
- Node detail view with live health check, incident, recommendation, and execution history
- Admin-only credential management with a full-width table layout
- Alerts page (work in progress, frontend wired) with a unified notification table and date/category filters
- Reports page (work in progress, frontend wired) with report previews and CSV/JSON export
- Settings page (work in progress, frontend wired) for model, API key override, LDAP/SSO, organization, notification, retention, and execution settings
- Validations and Remediations pages for reusable automation checks and approved remediation definitions
- Node-level automatic remediation playbooks with a no-code builder, validation-to-remediation connections, and left-to-right execution logic
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
- Validation-gated automatic remediation:
  - validations can execute through a node's runner or agent route
  - expected text can be written as natural language and evaluated by the model against command or HTTP output
  - connected remediations become eligible only when all linked validations match
  - the model selects from eligible remediations, with a deterministic single-remediation fallback when no model client is available
- Separate runner process for queued command execution
- `raven-flock` broker for enrolled Linux/Unix Flock agents
- `flock-test` development agent container for validating enrollment and brokered execution
- Audit logs and approval decision records

## Security Model

RAVEN keeps AI out of the direct execution path:

- AI can propose command cards, but it cannot execute them.
- Operators/Admins must explicitly approve a command card.
- Approved commands are written to `execution_tasks`.
- The `raven-runner` container polls queued tasks and performs execution.
- For agent-mode nodes, the runner dispatches approved work to `raven-flock`; enrolled agents poll Flock, execute locally, and return command results.
- Frontend code never executes shell commands.
- Command execution records include command preview, exit code, output, and post-action validation.
- OpenAI calls are limited to incident recommendation generation, validation-output evaluation, automation gate selection, and user/operator-prompted follow-up workflows.

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
- `FLOCK_INTERNAL_TOKEN`: shared internal token used by the runner to dispatch work to `raven-flock`.
- `FLOCK_ENROLLMENT_TOKEN`: enrollment token used by Linux/Unix agents during first join. Compose seeds `dev-flock-enrollment-token` for local development.

Docker Compose overrides `DATABASE_URL` to `sqlite:////data/raven.db` so backend, runner, and Flock share state through the `raven-data` volume.

## Docker Compose Deployment

The intended local deployment path is Docker Compose.

```bash
docker compose up --build -d --remove-orphans
```

Services:

- `raven-backend`: FastAPI API plus embedded monitoring loop
- `raven-runner`: approved command execution daemon
- `raven-flock`: Flock enrollment, heartbeat, policy, and task broker server
- `flock-test`: Linux/Unix development agent that enrolls with `raven-flock`
- `raven-frontend`: Next.js UI

Open:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

Check status:

```bash
docker compose ps
docker compose exec -T backend curl -fsS http://localhost:8000/api/health
docker compose exec -T flock curl -fsS http://localhost:8000/api/health
docker compose exec -T backend curl -fsSI http://frontend:3000/messages
```

Verify local Flock join and execution:

```bash
docker compose logs --tail=80 flock-test
docker compose exec -T flock curl -fsS \
  -H 'Content-Type: application/json' \
  -H 'X-Flock-Internal-Token: dev-flock-internal-token' \
  -d '{"target":"flock:flock-test","command":"uname -s","timeout_seconds":30}' \
  http://localhost:8000/api/flock/internal/dispatch
```

Successful local dispatch returns a JSON response with `status: "success"`, `exit_code: 0`, and Linux/Unix command output.

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

Flock server in another shell:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main_flock:app --reload --port 8001
```

Linux/Unix Flock agent in another shell:

```bash
cd backend
source .venv/bin/activate
FLOCK_SERVER_URL=http://localhost:8001/api/flock \
FLOCK_ENROLLMENT_TOKEN=dev-flock-enrollment-token \
FLOCK_AGENT_NAME=flock-test \
python -m app.services.flock_agent
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
docker compose exec -T flock curl -fsS http://localhost:8000/api/health
docker compose exec -T backend curl -fsSI http://frontend:3000/messages
docker compose exec -T flock curl -fsS -H 'Content-Type: application/json' -H 'X-Flock-Internal-Token: dev-flock-internal-token' -d '{"target":"flock:flock-test","command":"uname -s","timeout_seconds":30}' http://localhost:8000/api/flock/internal/dispatch
```

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
- `GET|POST /api/validations`
- `PUT|DELETE /api/validations/{id}`
- `POST /api/validations/{id}/test`
- `GET|POST /api/remediations`
- `PUT|DELETE /api/remediations/{id}`
- `POST /api/remediations/{id}/test-preview`
- `GET|PUT /api/nodes/{id}/automation-assignments`
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
- `GET /api/flock/agents`
- `PUT /api/flock/agents/{id}`
- `GET|POST /api/flock/policies`
- `PUT /api/flock/policies/{id}`

Flock agent-facing and internal broker endpoints are served by `raven-flock`:

- `POST /api/flock/enroll`
- `POST /api/flock/agents/{agent_id}/heartbeat`
- `POST /api/flock/agents/{agent_id}/tasks/claim`
- `POST /api/flock/agents/{agent_id}/tasks/{task_id}/result`
- `POST /api/flock/internal/dispatch`

## Message Center Workflow

1. Monitoring detects repeated health-check failures.
2. Backend creates an incident and internal alert message.
3. If the node has an automatic remediation playbook, backend runs assigned validations and evaluates connected remediation eligibility.
4. If playbook validations match, RAVEN can queue an automated remediation through the node's configured execution route.
5. AI generates the initial summary and three command cards using node context and failure details.
6. Operator approves or rejects one proposed command.
7. Runner executes approved or automated commands directly, or dispatches agent-mode work through Flock.
8. Backend performs post-action validation.
9. If validation is still unhealthy, AI generates a new short follow-up using raw command output.
10. If validation is healthy, UI shows:
   - `Close incident`: marks resolved and archives the conversation.
   - `Investigate further`: keeps the thread active and starts root-cause analysis.

Archived conversations remain available from the Archived tab.

## Execution Target Conventions

The runner supports transport-aware targets:

- `local:<subject>`
- `ssh:<host>:<subject>`
- `api:<endpoint>:<subject>`
- `flock:<agent-id-or-name>`

Examples:

- `local:raven-backend`
- `ssh:ops@app01:raven-web.service`
- `api:https://runner.example.internal:raven-api`
- `flock:flock-test`

The seeded MVP data uses `local:raven-backend`. Agent-mode nodes can use `flock:<agent-id-or-name>` to route approved commands through `raven-flock` to an enrolled Linux/Unix agent.

## Current Limitations

- SQLite is used for MVP simplicity. PostgreSQL is the likely production migration path.
- The monitoring loop currently runs inside the backend process.
- The runner executes commands available inside its own container or through SSH/API targets.
- The Flock agent workflow currently targets Linux/Unix. Windows enrollment and service installation are planned later.
- Local Compose uses development Flock tokens. Replace them before any shared or persistent deployment.
- Managing host Docker or host services from the runner requires explicit host integration.
- AI command proposals should still be reviewed carefully before approval.
