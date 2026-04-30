from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.config import get_settings
from app.models import Credential, FlockAgent, FlockEnrollmentToken, FlockMetric, FlockPolicy, FlockTask, Node, NodeHealthCheck, RemediationProfile, User


def seed_data(db: Session) -> None:
    settings = get_settings()
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

    for agent in db.query(FlockAgent).filter(FlockAgent.status == "unenrolled").all():
        node = db.query(Node).filter(Node.id == agent.node_id).first() if agent.node_id else None
        db.query(FlockMetric).filter(FlockMetric.agent_id == agent.id).delete(synchronize_session=False)
        db.query(FlockTask).filter(FlockTask.agent_id == agent.id).delete(synchronize_session=False)
        if node:
            db.delete(node)
        db.delete(agent)

    for node in (
        db.query(Node)
        .filter(Node.execution_mode == "agent", Node.execution_target.like("flock:%"), Node.is_enabled.is_(False))
        .all()
    ):
        linked = db.query(FlockAgent).filter(FlockAgent.node_id == node.id).first()
        if not linked and node.description == "Auto-enrolled Flock agent host.":
            db.delete(node)

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

    flock_policy = db.query(FlockPolicy).filter(FlockPolicy.name == "Default Linux/Unix Policy").first()
    if not flock_policy:
        flock_policy = FlockPolicy(
            name="Default Linux/Unix Policy",
            description="Default policy for Linux/Unix Flock agents enrolled through the local development workflow.",
            is_default=True,
            is_enabled=True,
            heartbeat_interval_seconds=10,
            task_timeout_seconds=60,
            command_allowlist=[],
        )
        db.add(flock_policy)
        db.flush()
    else:
        flock_policy.is_default = True

    for policy in db.query(FlockPolicy).filter(FlockPolicy.id != flock_policy.id, FlockPolicy.is_default.is_(True)).all():
        policy.is_default = False

    enrollment_secret = settings.flock_enrollment_token or "dev-flock-enrollment-token"
    enrollment_token = db.query(FlockEnrollmentToken).filter(FlockEnrollmentToken.name == "local-linux-unix-enrollment").first()
    if not enrollment_token:
        db.add(
            FlockEnrollmentToken(
                name="local-linux-unix-enrollment",
                token_hash=get_password_hash(enrollment_secret),
                policy_id=flock_policy.id,
                is_enabled=True,
            )
        )

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
        if not db.query(NodeHealthCheck).filter(NodeHealthCheck.node_id == node.id).first():
            db.add(
                NodeHealthCheck(
                    node_id=node.id,
                    name=f"{node.health_check_type.upper()} health",
                    check_type=node.health_check_type or "http",
                    config_json={
                        **({"url": node.url} if node.url else {}),
                        **({"path": node.health_check_path} if node.health_check_path else {}),
                        "expected_status_code": node.expected_status_code,
                        **({"expected_response_contains": node.expected_response_contains} if node.expected_response_contains else {}),
                    },
                    interval_seconds=node.check_interval_seconds,
                    timeout_seconds=node.timeout_seconds,
                    retry_count=node.retry_count,
                )
            )

    raven_test = db.query(Node).filter(Node.name == "Raven Test").first()
    if raven_test:
        db.delete(raven_test)

    db.commit()
