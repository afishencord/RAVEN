# Secure bootstrap and upgrades

RAVEN does not ship login credentials or working JWT/Flock secrets. Missing,
short, or known placeholder secrets prevent control-plane startup. New databases
require an explicitly provisioned administrator. An existing database is not an
instruction to reset passwords, reactivate users, or replace enrollment tokens.

## New local Docker installation

From the repository root, using a private interactive terminal:

```bash
python3 scripts/bootstrap_env.py
docker compose build
docker compose run --rm --no-deps backend python -m app.bootstrap init-admin
docker compose up -d
```

The helper creates `.env` with independent cryptographically random JWT, internal
Flock, and enrollment secrets. It uses exclusive creation, mode `0600`, does not
print secrets, and refuses to overwrite any existing file or symlink. `.env` is
ignored by Git. Do not run `cat .env`, `docker compose config`, or dump container
environments into logs/tickets: those can expose secrets. The example env file
is only a reference and deliberately cannot start the application.

The offline `init-admin` command prompts for your chosen username and a password
without echo. Use a unique password-manager-generated password or passphrase
between 16 and 72 UTF-8 bytes. The limit avoids bcrypt's silent truncation. The
command creates only an administrator, stores only a password hash, and refuses
to overwrite any existing user. It starts no service or background executor.
Do not use `-T`, pipe a password, or put it on the command line.

Open <http://localhost:3000> and sign in with the account you created. Host ports
are bound to loopback. Monitoring starts **disabled**; configure inventory and
review targets before explicitly setting `EMBEDDED_MONITORING=true`. The runner
is still an execution-capable service: do not approve work you do not intend to
run. The optional development agent is not started by default:

```bash
docker compose --profile agent up -d flock-test
```

New Flock policies have an empty command allowlist (deny all). Set a narrowly
reviewed allowlist before expecting any command dispatch to succeed; follow the
exact-command API workflow in [FLOCK_SECURITY.md](FLOCK_SECURITY.md). The agent
receives only enrollment configuration, never JWT or internal dispatch secrets.
Its persisted agent state is a credential; protect the named volume. The Compose
agent has a fixed hostname so container recreation does not change its identity.
For an existing agent volume enrolled under an old random container hostname,
keep that exact hostname through an explicit Compose override, or deliberately
unenroll/re-enroll the disposable test agent and replace its state. Do not silently
edit/reassign enrolled identity fields; conflicting enrollment is refused.

## Existing installations: plan a maintenance window

**Do not delete the database or run `docker compose down -v` to upgrade.** Preserve
a verified database/volume backup and protect configuration/agent-state backups.
Stop the old backend, runner, Flock server, and agents before updating code or
performing the offline commands below. Keep network access restricted throughout.

1. Replace any old JWT/internal secrets with independent random values in your
   secret manager or private `.env`; ensure backend, runner, and Flock receive
   the same intended settings. `python3 scripts/bootstrap_env.py --output
   .env.upgrade` creates a separate ignored private candidate without touching
   existing configuration. Preserve reviewed nonsecret deployment settings when
   adopting it. Never overwrite the current file without a backup/review.
2. Rotation of `JWT_SECRET_KEY` invalidates existing sessions. Users sign in
   again. Rotate it for former-demo deployments even if the old value happens
   to pass length validation. Coordinate internal-token rotation across all
   server/runner processes; do not leave old processes listening.
3. Build the new image and inspect the existing database offline:

   ```bash
   docker compose build
   docker compose run --rm --no-deps backend python -m app.bootstrap audit
   ```

   Audit is read-only and returns nonzero if any active account still matches a
   former public demo password (regardless of username) or an enabled enrollment
   token matches the former public enrollment secret. Only counts are printed.
   Startup refuses this known unsafe state **without changing any records**.
4. Reset each account you intend to keep, naming its existing username:

   ```bash
   docker compose run --rm --no-deps backend python -m app.bootstrap reset-password YOUR_EXISTING_USERNAME
   ```

   The password is prompted privately. Roles, account IDs, and active state are
   preserved; a reset never creates/reactivates an account. Reset at least one
   active administrator before disabling remaining demo access:

   ```bash
   docker compose run --rm --no-deps backend python -m app.bootstrap disable-demo-access
   docker compose run --rm --no-deps backend python -m app.bootstrap audit
   ```

   The disable command affects only accounts/tokens still matching former demo
   values, preserves their records, and refuses to leave no active non-demo
   administrator. Already-changed passwords and unrelated users/tokens are not
   touched. If no active administrator exists, stop and arrange a reviewed
   database recovery rather than bypassing the guard.
5. The env enrollment secret is **create-only**: it seeds the named initial
   enrollment record only if that record does not exist. Changing the env value
   does not rotate or re-enable an existing record. After disabling a legacy
   token, explicitly rotate and enable the initial record from your fresh private
   configured `FLOCK_ENROLLMENT_TOKEN` (the command never displays it):

   ```bash
   docker compose run --rm --no-deps backend python -m app.bootstrap rotate-enrollment
   ```

   Existing agent identities and policy assignments are preserved. Securely
   configure agents that still need to enroll with the new token. An agent with
   protected enrolled state does not need its old enrollment token to reconnect.
6. Review enrolled agents, inventory, policy allowlists, and audit history. A
   formerly public enrollment/internal/JWT secret may already have been used;
   this change cannot prove the old deployment was uncompromised. Revoke unknown
   agents and rotate retained agent credentials by an explicit reviewed
   unenrollment/re-enrollment workflow. Review any old `local-agent-token`
   placeholder credential and replace/remove it and dependent node configuration
   before enabling execution; upgrades do not silently delete inventory.
7. Start services, verify login and health, then enable only intended monitoring
   and agents. Existing non-demo users and password hashes are preserved.

## Non-Docker and noninteractive environments

The backend reads the repository-root `.env`, independent of the shell's working
directory. Install the locked backend dependencies, then from `backend/` run
`python -m app.bootstrap init-admin` before starting API/Flock/runner processes.
For local Flock use `FLOCK_SERVER_URL=http://localhost:8001/api/flock` in the private
configuration. External agents need only their Flock URL, unique agent name,
private state path, and a securely delivered enrollment token; **never distribute
JWT_SECRET_KEY or FLOCK_INTERNAL_TOKEN to agents**.

For a controlled unattended first start, a secret manager may supply both
`BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` (16–72 UTF-8 bytes).
`seed_data` creates exactly one administrator only when no users exist. Remove
these variables after initialization. Existing users are never overwritten or
supplemented by bootstrap variables. Serialize initial startup (initialize the
DB before launching multiple processes); the interactive command is recommended
for local Compose because it avoids retaining a plaintext administrator password
in environment configuration.

## Before broader deployment

This is not a production-readiness certification. Keep secrets outside images,
source control, build arguments, shell history, and shared logs. For production,
use a secret manager and review service-specific access rather than distributing
one local `.env` to every control-plane service. Use TLS, authentication/network
boundaries, least-privilege host/container identities, protected database and
agent-state volumes, restricted enrollment-token lifetimes/use, backups, and
reviewed operational rotation/recovery. The default Compose setup is local-only.
Flock broker/agent traffic beyond a trusted isolated network needs TLS and network
controls. Follow [SSH host verification](SSH_HOST_VERIFICATION.md) before enabling
SSH; never trust an unverified scanned host key. The API still permits powerful
administrative command execution, so review operator authorization and commands.
