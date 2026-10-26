#!/usr/bin/env python3
"""Create new, private local configuration without exposing generated secrets.

No application imports or third-party dependencies; never modifies an existing
file. This only writes configuration, and never touches a database or service.
"""

import argparse
import os
from pathlib import Path
import secrets


ROOT = Path(__file__).resolve().parents[1]


def create_env(path: Path) -> None:
    if not (path.name == ".env" or path.name.startswith(".env.")) or path.name == ".env.example":
        raise ValueError("Destination must be an ignored .env or .env.* file, never .env.example")
    values = {
        "DATABASE_URL": "sqlite:///./raven.db",
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "FLOCK_INTERNAL_TOKEN": secrets.token_urlsafe(48),
        "FLOCK_ENROLLMENT_TOKEN": secrets.token_urlsafe(48),
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "gpt-4.1-mini",
        "FRONTEND_ORIGIN": "http://localhost:3000",
        "EMBEDDED_MONITORING": "false",
        "DEBUG": "false",
        "MONITOR_POLL_SECONDS": "5",
        "RUNNER_POLL_SECONDS": "5",
        "NEXT_PUBLIC_API_BASE_URL": "http://localhost:8000/api",
    }
    # O_EXCL rejects existing files and symlinks; the file is never world-readable
    # even temporarily, regardless of the caller's umask.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("# Private local configuration. Do not commit, share, or print.\n")
        stream.write("".join(f"{key}={value}\n" for key, value in values.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".env", help="Private ignored .env destination; must not exist")
    args = parser.parse_args()
    try:
        create_env(args.output)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    except FileExistsError:
        parser.exit(1, "Refusing to overwrite existing configuration. See SECURITY_BOOTSTRAP.md for upgrades.\n")
    except OSError:
        parser.exit(1, "Cannot write private configuration; check the destination directory and permissions.\n")
    print("Created private configuration (mode 0600); generated secrets were not displayed.")
    print("Next, initialize an administrator before starting services. See SECURITY_BOOTSTRAP.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
