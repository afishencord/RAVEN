"""Offline initial-admin and legacy-demo remediation commands.

Never imports or starts listeners, monitoring, a runner, or an agent. Passwords
are read without echo from a terminal, never accepted as command-line arguments.
"""

import argparse
import getpass
import sys
import warnings

from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.config import AgentSettings, get_settings, validate_admin_password
from app.models import Credential, FlockEnrollmentToken, User

# Former public seed values are detection-only, never usable configuration or
# new account defaults. Check every username so renaming cannot evade migration.
LEGACY_DEMO_PASSWORDS = ("admin123!", "operator123!", "viewer123!")
LEGACY_ENROLLMENT_TOKEN = "dev-flock-enrollment-token"


def demo_access(db: Session) -> tuple[list[User], list[FlockEnrollmentToken]]:
    users = [
        user for user in db.query(User).filter(User.is_active.is_(True)).all()
        if any(verify_password(password, user.hashed_password) for password in LEGACY_DEMO_PASSWORDS)
    ]
    tokens = [
        token for token in db.query(FlockEnrollmentToken).filter(FlockEnrollmentToken.is_enabled.is_(True)).all()
        if verify_password(LEGACY_ENROLLMENT_TOKEN, token.token_hash)
    ]
    return users, tokens


def assert_no_demo_access(db: Session) -> None:
    users, tokens = demo_access(db)
    if users or tokens:
        raise RuntimeError(
            "Known legacy demo access is still enabled. Startup refused without changing records. "
            "Stop all services, back up the database, then use python -m app.bootstrap audit, "
            "reset-password USERNAME, and disable-demo-access. See SECURITY_BOOTSTRAP.md."
        )


def create_initial_admin(db: Session, username: str, password: str) -> None:
    if db.query(User).first():
        raise ValueError("Users already exist; initial bootstrap never overwrites an existing account")
    if not username or username != username.strip() or len(username) > 64:
        raise ValueError("Username must contain 1 to 64 characters without surrounding whitespace")
    validate_admin_password(password)
    db.add(User(username=username, full_name="RAVEN Administrator", role="admin", hashed_password=get_password_hash(password)))
    db.commit()


def reset_password(db: Session, username: str, password: str) -> None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise ValueError("No such user; password reset does not create or reactivate accounts")
    validate_admin_password(password)
    user.hashed_password = get_password_hash(password)
    db.commit()


def disable_demo_access(db: Session) -> tuple[int, int]:
    users, tokens = demo_access(db)
    demo_ids = {user.id for user in users}
    if not any(user.id not in demo_ids for user in db.query(User).filter(User.is_active.is_(True), User.role == "admin").all()):
        raise ValueError("Refusing to leave no active administrator; reset an existing active admin password first")
    for user in users:
        user.is_active = False
    for token in tokens:
        token.is_enabled = False
    db.commit()
    return len(users), len(tokens)



def rotate_enrollment(db: Session, secret: str | None) -> None:
    # This is deliberately explicit; merely changing an env var never reenables
    # a revoked token. Validate even when called outside the CLI.
    secret = AgentSettings(_env_file=None, flock_enrollment_token=secret).flock_enrollment_token
    if not secret:
        raise ValueError("Set a fresh private FLOCK_ENROLLMENT_TOKEN before rotating enrollment")
    token = db.query(FlockEnrollmentToken).filter(FlockEnrollmentToken.name == "local-linux-unix-enrollment").first()
    if not token:
        raise ValueError("No initial enrollment record exists; initialize the application with enrollment configured first")
    token.token_hash = get_password_hash(secret)
    token.is_enabled = True
    db.commit()


def _read_password() -> str:
    if not sys.stdin.isatty():
        raise ValueError("A private interactive terminal is required; do not pipe passwords or put them in arguments")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            password = getpass.getpass("New password (16 to 72 UTF-8 bytes): ")
            confirmation = getpass.getpass("Confirm password: ")
        except getpass.GetPassWarning:
            raise ValueError("Cannot safely hide input on this terminal") from None
    validate_admin_password(password)
    if password != confirmation:
        raise ValueError("Passwords did not match; nothing was changed")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-admin", help="Create the first user in an empty database, with private prompts")
    commands.add_parser("audit", help="Read-only check for enabled known demo accounts and enrollment tokens")
    reset = commands.add_parser("reset-password", help="Reset one existing account password without changing its role/active state")
    reset.add_argument("username")
    commands.add_parser("disable-demo-access", help="Explicitly disable only known demo-password users/tokens, preserving their records")
    commands.add_parser("rotate-enrollment", help="Replace and explicitly enable the initial enrollment token using FLOCK_ENROLLMENT_TOKEN")
    args = parser.parse_args()

    from app.database import Base, SessionLocal, engine, migrate_sqlite_schema

    try:
        if args.command == "init-admin":
            if not sys.stdin.isatty():
                raise ValueError("A private interactive terminal is required to initialize an administrator")
            Base.metadata.create_all(bind=engine)
            migrate_sqlite_schema()
        with SessionLocal() as db:
            if args.command == "init-admin":
                if db.query(User).first():
                    raise ValueError("Users already exist; initial bootstrap never overwrites an existing account")
                username = input("Administrator username: ")
                create_initial_admin(db, username, _read_password())
                print("Initial administrator created. No password was displayed or saved to configuration.")
            elif args.command == "audit":
                users, tokens = demo_access(db)
                print(f"Enabled known demo access: {len(users)} account(s), {len(tokens)} enrollment token(s).")
                placeholders = db.query(Credential).filter(Credential.kind == "agent_token", Credential.secret_value == "replace-me").count()
                if placeholders:
                    print(f"Warning: {placeholders} legacy placeholder outbound credential(s); review references and replace/remove before execution.")
                return 1 if users or tokens else 0
            elif args.command == "reset-password":
                reset_password(db, args.username, _read_password())
                print("Password reset. Role and active state preserved. Rotate JWT_SECRET_KEY to revoke existing sessions.")
            elif args.command == "rotate-enrollment":
                rotate_enrollment(db, get_settings().flock_enrollment_token)
                print("Initial enrollment token rotated and enabled; existing agent identities and policies preserved.")
            else:
                user_count, token_count = disable_demo_access(db)
                print(f"Disabled {user_count} demo account(s) and {token_count} demo enrollment token(s); records preserved.")
        return 0
    except (ValueError, EOFError) as exc:
        parser.exit(1, f"{exc}\n")
    except KeyboardInterrupt:
        parser.exit(1, "Canceled.\n")
    except Exception:
        # Database exception text can contain SQL parameters/password hashes.
        parser.exit(1, "Operation failed; verify database/configuration and backup before retrying. No secret details displayed.\n")


if __name__ == "__main__":
    raise SystemExit(main())
