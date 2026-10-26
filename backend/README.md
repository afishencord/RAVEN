# Backend dependencies and regression tests

Use Python 3.12, matching the backend Docker image. `requirements.in` contains
maintainable direct pins; generated `requirements.txt` locks the complete runtime
graph, including platform markers and SHA-256 distribution hashes. Install the
lock, not the input file:

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app tests
```

The tests use Python's standard-library `unittest`; no extra test dependencies are
needed. They replace application settings with public test fixtures and use an
isolated in-memory SQLite database. Monitoring is disabled, no runner or Flock
agent is started, and no live OpenAI, SSH, or health-check calls are made. Tests
cover JWT validation, login and role enforcement, response schemas, JSON request
validation, CORS, OpenAPI, and both API/Flock lifespans. Starlette 1.10 currently
emits a deprecation warning for its HTTPX-based TestClient; HTTPX remains pinned
for the application's existing HTTP clients, and this does not fail the tests.

To refresh the lock, use `uv` (generated with 0.13.4) and rerun the checks above:

```bash
uv pip compile requirements.in --generate-hashes --no-build \
  --python-version 3.12 --universal --no-python-downloads \
  --default-index https://pypi.org/simple --output-file requirements.txt
```

Add `--upgrade` when intentionally refreshing existing transitive pins. Review
the resulting versions and advisory data before installing. Docker also uses
`--require-hashes --only-binary=:all:` so builds cannot silently resolve another
graph or run source-package build hooks. The lock is portable across platform
markers, but verification for this change used Linux x86-64/Python 3.12; other
platforms must be tested separately. Base image digests and operating-system
packages are not covered by this Python dependency lock.

## Authentication migration

- `PyJWT==2.15.1` replaces `python-jose[cryptography]`; `python-jose`, `ecdsa`,
  `rsa`, `pyasn1`, and the now-unused `cryptography` tree are absent from the lock.
- Existing **HS256 tokens remain valid** with the same secret, username, and
  expiration. The payload and bearer response format are unchanged. Tests verify
  JOSE compact/HMAC compatibility independently with standard-library HMAC,
  without bringing the retired library back as a test dependency.
- `JWT_ALGORITHM` now explicitly permits only `HS256` (default), `HS384`, or
  `HS512`, appropriate for RAVEN's single shared-secret setting. Unsupported,
  unsigned, and asymmetric algorithm settings fail configuration validation.
  **Deployments that previously configured RSA/ECDSA/other asymmetric JWTs must
  not treat this as a transparent upgrade.** They need a separate reviewed
  public/private-key configuration design or a planned HMAC migration with
  reauthentication. The verifier never chooses an algorithm or key from token
  headers and never mixes HMAC and asymmetric algorithms.
- `sub` and `exp` are required; the subject must be a nonempty string. RAVEN
  already issued both claims. Handcrafted tokens without expiration are now
  rejected. Expired, malformed, wrong-signature, future-validity, wrong-audience,
  unsigned, and algorithm-confusion tokens fail authentication.
- Inactive users now receive the same generic 401 at login as invalid
  credentials. Previously they could receive a token that `/auth/me` rejected.
  Role and active status still come from the database on every authenticated
  request, not from token role claims.
- Password hashing is unchanged (`passlib==1.7.4`, `bcrypt==4.0.1`) to preserve
  existing hashes. Moving to another password hashing library is separate work.
- Keep a strong, private `JWT_SECRET_KEY` outside source control. No deployment
  secret or default credential is changed by these code changes. Rotating the
  secret intentionally invalidates previously issued tokens.

## Dependency security updates

- FastAPI **0.162.0**, with an explicit Starlette **1.10.0** pin, removes the old
  FastAPI upper bound that prevented installing the patched Starlette line.
- python-multipart **0.0.32** replaces 0.0.20. Login still takes JSON, not form
  data; retaining the patched dependency avoids unexpected optional-parser gaps.
- Other direct runtime versions remain unchanged to avoid unrelated SDK,
  database, password-hashing, or server migrations.

References: [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/),
[Starlette releases](https://www.starlette.io/release-notes/),
[python-multipart on PyPI](https://pypi.org/project/python-multipart/0.0.32/),
[PyJWT verification guidance](https://pyjwt.readthedocs.io/en/stable/api.html#jwt.decode).
