# Flock command and identity safeguards

These changes intentionally tighten compatibility. Upgrade the **broker and every
agent** before allowing work, and stop/drain execution during the upgrade. Do not
mistake a successfully enrolled or online agent for authorization to run commands.

## Command policy contract

- An agent must have an explicitly assigned, enabled policy. Removing the
  assignment does **not** inherit a default; a missing, disabled, empty or malformed
  policy denies commands (exit code `126`). Defaults are selected only at first
  enrollment, and no policy is silently created or substituted.
- `command_allowlist` entries are **complete argument vectors**, expressed as quoted
  command strings. The broker and agent both use the same POSIX quoting parser and
  require an exact match of the executable and **every** argument. Whitespace and
  quoting may vary only if they produce the same argv. Entries are not command
  prefixes, regular expressions, globs, shell snippets or argument templates.
- Executables must be canonical absolute paths. Shell operators, expansions,
  wildcards and control characters are rejected. Known shells/interpreters,
  privilege wrappers and remote/container transports are unsupported. The agent
  executes the validated argv with `shell=False`, closed stdin, and **no automatic
  sudo**. It retains the configured agent account's privileges; this patch does
  not make an agent running as root unprivileged.
- Task timeouts must be valid positive integers, bounded by the policy's
  `task_timeout_seconds` (1–86400). A malformed entry or timeout denies the whole
  policy rather than partially interpreting it.
- Authorization is checked when dispatching **and again when claiming** a queued
  command. A denied queued task is marked failed and never delivered for execution.
  Each claimed command carries its current policy snapshot, which the agent
  independently checks immediately before spawning. An old broker that omits the
  snapshot fails closed with an upgraded agent. A heartbeat policy is never used
  as a fallback. Unknown task types are rejected; authenticated `unenroll` control
  tasks remain available even when command execution is disabled.
- Policy revocation prevents newly dispatched/claimed work. It cannot cancel a
  process already executing or a claim already returned over the network. Stop
  affected agents as part of an emergency response requiring in-flight cancellation.

Existing empty allowlists now authorize **nothing**. Previously working prefix,
relative-path, shell, `sudo`, or remotely wrapped entries must be replaced with
reviewed exact commands; do not mechanically copy arbitrary queued work into a
policy. For example, one policy could explicitly authorize only:

```json
{
  "is_enabled": true,
  "task_timeout_seconds": 30,
  "command_allowlist": [
    "/usr/bin/systemctl --no-pager status example.service"
  ]
}
```

Verify the executable path and arguments on the target host before authorizing
this example; it is not a command to run as part of installation. A `restart`
operation, a different service, or any additional flag would need a separate
explicit entry. Prefer noninteractive, single-purpose programs and flags such as
`--no-pager`. Executables, their configuration and referenced scripts/files must
be administrator-controlled and not writable by untrusted users. Exact argv
matching is **not an OS sandbox** or a proof that a deliberately approved program
is harmless; it does not inspect symlink targets or constrain all behavior of that
program. Do not authorize alternate aliases that hide an interpreter/wrapper.

The current UI can assign policies but does not edit allowlists. An authenticated
**administrator** can `PUT /api/flock/policies/{policy-id}` with the JSON above
using an authenticated API client or the backend's `/docs` interface. Keep the
admin bearer token private (not in shell arguments, shared scripts or screenshots).
`PUT /api/flock/agents/{database-id}` with `{"policy_id": <policy-id>}` explicitly
assigns it. Setting `is_enabled` to false or `command_allowlist` to `[]` disables
commands without preventing heartbeat or controlled unenrollment.

The broker is the source of policy; the snapshot is not a separately signed or
host-pinned policy. Use certificate-verified **HTTPS** for agent/broker traffic on
any untrusted network, protect broker ingress/internal tokens, and restrict the
agent service's OS privileges. The provided internal Compose HTTP network is not
an authenticated transport against an attacker who controls that network. These
application checks do not claim to solve a compromised broker or host.

## Enrollment and stable identity

A shared enrollment token permits creating a **new** identity only. Reusing an
existing normalized name **or** hostname returns HTTP `409`, without modifying
its ID, agent credential, policy, metadata, inventory or queued tasks. Enrollment
never rotates/replaces another agent's token or rebinds its task queue.

Names and hostnames have separate database-enforced unique keys (Unicode NFKC,
case-folded, surrounding whitespace removed; hostnames also ignore final dots).
The database constraints, not just a lookup, prevent concurrent enrollment races,
including requests with different enrollment tokens. Public agent IDs remain
immutable. Prefer `flock:<public-agent-id>` execution targets; ambiguous human
name/hostname/numeric aliases fail closed rather than selecting the first match.
Heartbeat cannot change the enrolled hostname. A host rename is an explicit
administrative inventory/recovery operation, not a way to claim a different host.
Container agents need a stable configured hostname across recreation. New
`flock-test` deployments use the stable Compose hostname `flock-test`; an existing
state volume enrolled under an old generated Docker hostname must retain that
previous hostname through an explicit Compose override, or undergo deliberate
administrator recovery/reenrollment. Changing the hostname while retaining its
old state intentionally fails with `409` rather than rebinding the record.

An existing agent normally restarts using its saved ID/token; it does not enroll
again. An idempotent explicit rejoin uses `POST /api/flock/enroll` with the usual
valid enrollment token and matching name/hostname plus `existing_agent_id`, and
`Authorization: Bearer <that agent's existing token>`. Proof for another ID or a
missing/wrong token fails with `401`; changed identity fields or pending
unenrollment fail with `409`. Successful proof preserves the **same** ID, token,
policy, metadata and inventory. An unenrolled agent cannot rejoin with old proof.

Lost credentials are **not** recovered by deleting the local state and resending
the shared enrollment token. Restore the original private state from a trusted
backup or ask an administrator to investigate and explicitly retire/recover the
record. This change adds no automatic lost-key recovery endpoint. Existing admin
unenrollment requires the old agent to acknowledge; do not silently delete a
record or transfer its pending tasks to a replacement host. Any offline database
reconciliation requires a backup and deliberate administrator review of agent,
inventory and task ownership.

## State file and schema migration

New agent state is atomically replaced with mode `0600`; newly created parent
folders use mode `0700`. The agent refuses symlink, nonregular, wrong-owner,
group/world-accessible, malformed or incomplete state instead of treating it as a
fresh enrollment. Before upgrading an existing agent, preserve its state token,
verify the file is a legitimate regular file owned by the service account, and
restrict permissions to `0600`. Restrict access to the state directory too. If a
state token was exposed, private permissions alone do not revoke copied tokens;
plan explicit credential recovery/retirement before allowing commands.

For the supported SQLite deployment, startup adds normalized identity columns and
unique indexes without changing existing public IDs, tokens or queues. It first
checks for invalid/duplicate normalized identities and stops with the conflicting
row IDs. It does **not** merge, delete, rename or rotate records to make migration
pass. Back up the database, stop old writers, investigate the reported records,
and deliberately reconcile ownership before retrying. Already unique databases
upgrade idempotently. Other database engines need a separately reviewed schema
migration before upgrade; the built-in migrator targets SQLite only.

## Verification

From `backend/`, run:

```sh
.venv/bin/python -m unittest tests.test_flock_security -v
```

The suite uses isolated in-memory/temporary SQLite databases and mocked subprocess
execution. It covers exact matches, shell/prefix/argument bypasses, missing and
revoked policy, queue-time revocation, unsupported task types, enrollment collision
and proof preservation, hostname rebinding, alias ambiguity, simultaneous inserts,
non-destructive migration, and private state. It does not run managed-host commands,
SSH, a real agent, or any production database migration.
