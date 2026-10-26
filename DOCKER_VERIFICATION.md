# Disposable Docker verification

This runs the **actual backend and frontend Dockerfiles**, then a real five-service Compose deployment. It is separate from the host-process smoke test in [LOCAL_VERIFICATION.md](LOCAL_VERIFICATION.md). Passing harness unit tests alone does **not** mean Docker passed.

## Run

Use a clean checkout on Linux with Python 3.10+, Docker Engine at `/var/run/docker.sock`, and Docker Compose **2.24.4+**. Ports `127.0.0.1:8000` and `127.0.0.1:3000` must be free. No application `.env`, account, repository secret, registry login, external node, or SSH target is needed.

```bash
python3 -m unittest discover -s scripts/tests -v
python3 scripts/docker_smoke.py
```

The harness refuses remote Docker contexts and frontend `.env*` files (the existing frontend Dockerfile copies its build context). It never modifies the existing Compose file, Dockerfiles, or application data. Compose's original service definitions are merged with a private, temporary test override; the effective merged configuration is validated before building or starting anything. `!override` is important: ordinary Compose list merging could retain the original public ports and `.env` file.

## Safety and lifecycle

- Generates fresh JWT/Flock secrets and role passwords; pre-populates all three users **before** seed/startup can create demo credentials or open listeners. Explicitly tests rejection of demo passwords and development Flock tokens.
- Uses random project-scoped data/agent-state volumes and container names. No existing database or service is reused. Bind mounts are limited to read-only test inputs. Secret files live under a private `0700` temporary directory; the individual password file is read-only `0444` so the capability-restricted container can read its mount.
- Makes only the API/UI reachable on loopback (native mappings when effective, otherwise the fixed relay below). Flock remains internal. All runtime containers use an internal Docker network, dropped capabilities, and `no-new-privileges`; image builds alone need network access to fetch public images/dependencies.
- Disables monitoring, clears the AI key, disables generated nodes/checks, and verifies zero health-check executions. Starts the real runner only against an empty disposable queue. Starts the real test agent only after empty-queue assertions; tests enrollment and two metric heartbeats. No executable task, SSH command, real AI request, or external probe is submitted.
- Synthetic Flock tests exercise auth, enrollment, heartbeat, inventory, empty claims and a **nonexistent** dispatch target. The latter must create no task. Auto-enrolled node checks are disabled again after enrollment.
- Suppresses Docker container logs; prints static summaries and credential-free test diagnostics, not credentials, HTTP bodies, resolved config, database contents, or application logs. Failed builds can print a limited diagnostic tail with generated values redacted. No artifacts/caches/images are published.
- Relay cleanup terminates the tracked child and all of its sockets. The `always()` retry also checks the saved PID start time and exact command before signalling it, so a reused PID is never killed. No traffic is logged.
- `finally` cleanup stops only this random project and removes its volumes, network, local image tags and secret files. It verifies no project-labelled containers/volumes/networks remain. Partial file preparation rolls back. GitHub's `always()` step retries cleanup after cancellation/failure. SIGKILL/host failure cannot guarantee cleanup; if Docker removal fails, the private state is retained for retry rather than hiding the failure.

For an explicit recoverable state location, choose a **new**, unused temporary directory:

```bash
python3 scripts/docker_smoke.py --state-dir /tmp/raven-my-disposable-check
# Only if an interrupted/failed cleanup left that directory:
python3 scripts/docker_smoke.py --cleanup --state-dir /tmp/raven-my-disposable-check
```

Never print or upload the contents of that directory.

## Internal network and host loopback topology

Docker can accept a loopback publishing request but omit its effective mapping when a container is attached only to an internal network. The harness checks actual process state and `NetworkSettings.Ports`, not just the requested Compose configuration. It logs only allowlisted state, exit/OOM/restart counts and binding counts, then requires HTTP readiness inside the container network.

If and only if a service's effective mapping is absent, a small standard-library TCP relay binds `127.0.0.1:8000` and/or `127.0.0.1:3000`. Its sole destinations are the exact inspected private IPv4s of this project's backend/frontend, on fixed ports 8000/3000. The project/service labels and sole internal-network membership are verified first. The relay cannot select targets from incoming traffic. An unexpected mapping, occupied port, dead service or failed relay is an error, not a reason to skip checks or weaken isolation. Loopback API, frontend and image-optimizer HTTP checks remain required, including the browser's compiled API address.

This preserves container egress isolation while exercising the real images through loopback. It is a **test topology**, not proof of native port publishing or production Compose defaults. The default deployment uses different network settings. See Docker's [internal-bridge host access documentation](https://docs.docker.com/engine/network/port-publishing/#gateway-modes) and Moby's internal-network early returns in the [iptables](https://github.com/moby/moby/blob/master/daemon/libnetwork/drivers/bridge/internal/iptabler/port.go) and [nftables](https://github.com/moby/moby/blob/master/daemon/libnetwork/drivers/bridge/internal/nftabler/port.go) port rules.

## Required checks

1. Build backend and frontend images using the repository Dockerfiles and lockfiles.
2. Run backend `unittest` inside its built image; run frontend typecheck and dependency/CSS/native Sharp unit tests inside its built image.
3. Seed random users without published ports, then start backend, Flock, frontend and idle runner.
4. Inspect service process/binding state, require internal readiness, establish native or fixed-relay loopback routing, then verify host loopback readiness and in-container health/auth/all-role permissions/read APIs/CORS/safe group CRUD. Check synthetic Flock and broker/API shared inventory.
5. Fetch ten frontend HTML routes and exercise the live Next.js image optimizer. Confirm the browser API address is compiled as `http://127.0.0.1:8000/api`.
6. Start the actual disposable agent and verify two metric heartbeats, all five processes running without restarts, and zero execution/Flock tasks or monitoring results.
7. Remove and verify all project resources and private inputs.

The HTTP suite intentionally mirrors safe assertions in `scripts/local_smoke.py`; it runs against the **built containers**, not host Python/Node processes. Anonymous HTML checks are **not authenticated browser-interaction QA**. Optional visual/browser testing requires the supported CUA environment; it is not available in this GitHub job, and no standalone browser driver is installed. Production readiness, TLS, real monitoring, SSH, AI output, command execution and production configuration are not claimed.

## GitHub Actions

`.github/workflows/docker-verification.yml` runs on pushes to `security/dependency-refresh-2026-10` and manual dispatch. It uses an ephemeral Ubuntu runner, a 35-minute timeout, only `contents: read`, checkout without persisted credentials, no repository secrets and no privileged PR trigger. There are no upload or image-push steps. A push can start it before manual dispatch becomes available on the default branch.

Checkout is pinned to official `actions/checkout` **v7.0.1**, full SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`, verified on 2026-10-26 against its [release](https://github.com/actions/checkout/releases/tag/v7.0.1) and [commit](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1). See official [checkout credentials/permissions guidance](https://github.com/actions/checkout/blob/v7.0.1/README.md), [Compose override semantics](https://docs.docker.com/reference/compose-file/merge/#replace-value), and [internal networks](https://docs.docker.com/reference/compose-file/networks/#internal).

## Verification status when added

Local syntax checks and the initial 13 stdlib safety-harness tests passed. The generated override and workflow parsed as YAML. Docker CLI/daemon are unavailable in the authoring environment, so **image builds, container tests and deployment checks have not run locally**. Their result must be read from the workflow for the exact published commit before describing Docker verification as passed.

The [first fork CI run](https://github.com/dot-fishencord/RAVEN/actions/runs/40410740429) built both images, passed 29 backend tests and the frontend typecheck/unit tests, and preseeded random accounts. It then timed out on the original loopback-readiness assumption; cleanup passed. The relay/diagnostic correction passed local safety/socket/lifecycle tests, but needs a new exact-commit CI result before the complete deployment can be called verified.
