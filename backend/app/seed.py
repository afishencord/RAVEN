from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.models import Credential, Node, RemediationProfile, User


def seed_data(db: Session) -> None:
    if not db.query(User).first():
        db.add_all(
            [
                User(username="admin", full_name="RAVEN Admin", hashed_password=get_password_hash("admin123!"), role="admin"),
                User(username="operator", full_name="Primary Operator", hashed_password=get_password_hash("operator123!"), role="operator"),
                User(username="viewer", full_name="Read Only User", hashed_password=get_password_hash("viewer123!"), role="viewer"),
            ]
        )

    if not db.query(RemediationProfile).filter(RemediationProfile.name == "command-executor").first():
        db.add(
            RemediationProfile(
                name="command-executor",
                description="Compatibility profile used for approved command execution.",
                allowed_action_keys=["approved_command"],
                allowed_targets=["*"],
                approval_required=True,
                cooldown_seconds=0,
                retry_limit=1,
                post_action_validation={"mode": "rerun_health_check"},
            )
        )

    credential = db.query(Credential).filter(Credential.name == "local-agent-token").first()
    if not credential:
        credential = Credential(
            name="local-agent-token",
            kind="agent_token",
            description="Example credential for a node-local agent endpoint.",
            secret_value="replace-me",
            metadata_json={},
        )
        db.add(credential)
        db.flush()

    defaults = {
        "Marketing Web": {
            "execution_mode": "runner",
            "execution_target": "local:raven-backend",
            "context_text": "raven-backend: FastAPI API container serving health checks on localhost:8000.",
            "approved_command_policy": "Prefer single-container diagnostics and restarts. Avoid destructive filesystem commands.",
        },
        "Orders API": {
            "execution_mode": "runner",
            "execution_target": "local:raven-backend",
            "context_text": "orders-api: API health endpoint served by the RAVEN backend for staging validation.",
            "approved_command_policy": "Diagnostics and targeted service restarts are allowed. Keep commands single-purpose.",
        },
        "Edge Host": {
            "execution_mode": "runner",
            "context_text": "edge-host: reachability probe against 127.0.0.1 for network diagnostics.",
            "approved_command_policy": "Allow only non-destructive network diagnostics.",
        },
    }
    for node in db.query(Node).all():
        node.remediation_profile = "command-executor"
        for key, value in defaults.get(node.name, {}).items():
            setattr(node, key, value)

    raven_test = db.query(Node).filter(Node.name == "Raven Test").first()
    if raven_test:
        db.delete(raven_test)

    db.commit()
