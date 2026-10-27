# SSH host verification and migration

**Breaking change:** runner commands and automation validations now refuse SSH
unless `SSH_KNOWN_HOSTS_PATH` points to an administrator-provisioned trust file.
Existing targets that relied on first-use acceptance, `~/.ssh/config`, or an
implicit `~/.ssh/known_hosts` file will stop working until migrated. Local, API,
and Flock execution routes do not require this setting.

Both SSH routes use the same implementation in
`backend/app/services/ssh_execution.py`. It explicitly sets
`StrictHostKeyChecking=yes`, uses a private 0600 snapshot copied directly from
the validated known_hosts file descriptor, and turns off automatic key updates
and DNS-based trust. The snapshot prevents a replaced source pathname from
changing trust between validation and SSH startup and is deleted after execution. Unknown and changed keys
are failures, never a prompt, retry with weaker settings, or automatic enrollment.
These options use OpenSSH's [host verification semantics](https://man.openbsd.org/ssh_config#StrictHostKeyChecking).

## Provision trust before enabling SSH

1. For every target, obtain its **public host key** and SHA-256 fingerprint from
   an independently authenticated administrative console, a verified management
   channel, or your trusted provisioning inventory. Do not copy a host's private
   key. On the server's trusted console, an administrator can inspect the public
   fingerprint with:

   ```sh
   ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
   ```

2. Independently compare that fingerprint with the received public key:

   ```sh
   ssh-keygen -lf ./app01_host_ed25519.pub -E sha256
   ```

   The fingerprint must match the verified source, not just a value returned by
   the same untrusted network connection. Keep the approver, target, fingerprint,
   and verification source in your change record. See
   [`ssh-keygen` fingerprint inspection](https://man.openbsd.org/ssh-keygen#l).
   **Do not pipe `ssh-keyscan` output directly into the trust file.** RAVEN does
   not run keyscan or silently trust newly observed keys.

3. Build a reviewed known_hosts file using each exact DNS hostname or IPv4
   address used in RAVEN's execution target. Its entries have this form (replace
   the placeholder with the verified base64 public key):

   ```text
   app01.example.test ssh-ed25519 <verified-public-key-base64>
   ```

   Add separately verified entries for additional target aliases or IP addresses.
   Do not add broad wildcard trust as a workaround. Keep an operator-controlled
   authoritative copy outside the application database and application-writable
   directories. Provision the runtime file owned by root or the application UID,
   readable by the application, and not writable by group or other users. Mount
   it read-only in containers. A non-empty regular file is required; missing,
   unreadable, empty, insecurely writable, and device/FIFO paths are rejected.

4. Set `SSH_KNOWN_HOSTS_PATH` to the absolute runtime filename. Only literal
   paths containing letters, digits, `_`, `.`, `/`, and `-` are accepted (including
   after resolving a symlink). No `~`, whitespace, `%` tokens, environment-variable
   expansion, or multiple filenames are supported. Example:

   ```dotenv
   SSH_KNOWN_HOSTS_PATH=/run/raven-ssh/known_hosts
   ```

## Docker Compose: mount into both executing services

The backend executes automation validations; the runner executes approved
commands. **Both need the same verified trust bundle.** The default Compose file
intentionally does not provision host trust or require SSH for unrelated routes.
After separately provisioning `/etc/raven/ssh/known_hosts` on the deployment host,
an operator can use this override file (`compose.ssh.yml`):

```yaml
services:
  backend:
    environment:
      SSH_KNOWN_HOSTS_PATH: /run/raven-ssh/known_hosts
    volumes:
      - type: bind
        source: /etc/raven/ssh
        target: /run/raven-ssh
        read_only: true
        bind:
          create_host_path: false
  runner:
    environment:
      SSH_KNOWN_HOSTS_PATH: /run/raven-ssh/known_hosts
    volumes:
      - type: bind
        source: /etc/raven/ssh
        target: /run/raven-ssh
        read_only: true
        bind:
          create_host_path: false
```

Start the intended deployment with both configuration files, for example
`docker compose -f docker-compose.yml -f compose.ssh.yml up -d --build`.
Protect the source directory from untrusted writes. Mounting the directory
rather than a single file allows an operator's atomic file replacement to become
visible inside both services. If using a single-file bind instead, remount or
recreate the services after replacement and verify they see the new file.

For a non-container deployment, configure the same setting and permissions for
both backend and runner processes. Installing trust on a developer laptop alone
is not enough: it must exist in the actual execution environment.

## Target and authentication compatibility

- Targets remain `ssh:host:subject` or `ssh:user@host:subject`, for DNS hostnames
  or IPv4 addresses on port 22. URI-style destinations, embedded options, ports,
  and IPv6 literals are not supported by this target grammar. Malformed SSH
  targets fail closed instead of falling back to local execution.
- The credential username is used when supplied; an embedded target username
  must match it. Otherwise the embedded username is used, or `root` for existing
  credentials without either username. Prefer an explicit least-privilege user.
- System/user SSH configuration is deliberately bypassed with `-F /dev/null`;
  implicit host aliases, jump hosts, proxy commands, extra identities, or custom
  ports from those files no longer apply. Use a directly reachable, resolvable
  hostname with its own verified trust entry. See [`ssh -F`](https://man.openbsd.org/ssh#F).
- Key authentication uses only the supplied key, in a temporary 0600 file removed
  after success, failure, or timeout. Password authentication remains available
  through `sshpass`, but its password is passed via a private file descriptor,
  never command-line arguments or an environment variable. Passwords containing
  line breaks are rejected; key passphrase prompting and interactive MFA are not
  supported. Host trust is required before either authentication route.

## Rotation and unexpected failures

For a planned host-key rotation, verify the replacement public key and fingerprint
out of band as above. Review a staged trust bundle, deploy it atomically to both
services, and coordinate the server-key change. A short overlap of independently
verified old and new keys is appropriate only for a planned rotation. Remove the
retired key when the migration is complete. Keep an audit record and verify the
bundle visible to each service before resuming queued SSH work.

An unexpected changed-key warning is a security incident to investigate, not
permission to delete the old entry. Pause affected SSH work, confirm the server's
identity through a trusted channel, and replace trust only after authorization.
For a compromised key, revoke/remove its trust immediately; do not retain it for
an overlap. Do not weaken host checking or accept a newly scanned key to restore
service. RAVEN never modifies the trust file itself.

Missing trust configuration fails locally before spawning SSH. OpenSSH/sshpass
host-key failures retain their nonzero exit status and diagnostic output, with
no fallback authentication or alternate trust file. An operator should validate
a permitted benign command through **both** application paths after deployment.
Do not assume a successful login on another machine proves RAVEN's trust setup.

## Regression coverage

Run `cd backend && .venv/bin/python -m unittest tests.test_ssh_execution -v`.
Tests mock subprocess execution: they inspect both routes/authentication modes,
strict SSH options, malformed/unsafe paths and destinations, private credential
handling and cleanup, and propagation of simulated unknown/changed-key failures
without fallback. They do not contact a host or prove a deployment's actual keys,
mounts, networking, SSH daemon, or credentials; those require the separately
verified operator acceptance check above.
