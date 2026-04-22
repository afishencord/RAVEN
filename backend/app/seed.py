from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.models import Node, RemediationProfile, User


def seed_data(db: Session) -> None:
    if not db.query(User).first():
        db.add_all(
            [
                User(username="admin", full_name="RAVEN Admin", hashed_password=get_password_hash("admin123!"), role="admin"),
                User(username="operator", full_name="Primary Operator", hashed_password=get_password_hash("operator123!"), role="operator"),
                User(username="viewer", full_name="Read Only User", hashed_password=get_password_hash("viewer123!"), role="viewer"),
            ]
        )

    if not db.query(RemediationProfile).first():
        db.add_all(
            [
                RemediationProfile(
                    name="webapp-basic",
                    description="Basic web application remediation profile for systemd-based services.",
                    allowed_action_keys=["restart_systemd_service", "clear_app_cache", "run_diagnostic_script", "curl_validation_check"],
                    allowed_targets=["local:raven-web.service", "local:raven-cache"],
                    approval_required=True,
                    cooldown_seconds=300,
                    retry_limit=1,
                    post_action_validation={"mode": "rerun_health_check"},
                ),
                RemediationProfile(
                    name="api-basic",
                    description="API service profile for containerized services.",
                    allowed_action_keys=["restart_container", "run_diagnostic_script", "curl_validation_check"],
                    allowed_targets=["local:raven-api", "local:raven-worker"],
                    approval_required=True,
                    cooldown_seconds=300,
                    retry_limit=1,
                    post_action_validation={"mode": "rerun_health_check"},
                ),
                RemediationProfile(
                    name="host-basic",
                    description="Host reachability profile for node and network diagnostics.",
                    allowed_action_keys=["run_diagnostic_script", "restart_process"],
                    allowed_targets=["local:nginx", "local:system-network"],
                    approval_required=True,
                    cooldown_seconds=600,
                    retry_limit=1,
                    post_action_validation={"mode": "rerun_health_check"},
                ),
            ]
        )

    if not db.query(Node).first():
        db.add_all(
            [
                Node(
                    name="Marketing Web",
                    description="Demo web node checking the RAVEN service health endpoint.",
                    environment="prod",
                    host="localhost",
                    port=8000,
                    url="http://localhost:8000",
                    health_check_type="http",
                    health_check_path="/health",
                    expected_status_code=200,
                    expected_response_contains="ok",
                    check_interval_seconds=60,
                    timeout_seconds=5,
                    retry_count=3,
                    remediation_profile="webapp-basic",
                    execution_target="local:raven-web.service",
                    is_enabled=True,
                ),
                Node(
                    name="Orders API",
                    description="Demo API node checking the RAVEN API health endpoint.",
                    environment="staging",
                    host="localhost",
                    port=8000,
                    url="http://localhost:8000",
                    health_check_type="api",
                    health_check_path="/api/health",
                    expected_status_code=200,
                    expected_response_contains="healthy",
                    check_interval_seconds=45,
                    timeout_seconds=5,
                    retry_count=2,
                    remediation_profile="api-basic",
                    execution_target="local:raven-api",
                    is_enabled=True,
                ),
                Node(
                    name="Edge Host",
                    description="Network edge host reachability check.",
                    environment="prod",
                    host="127.0.0.1",
                    health_check_type="ping",
                    check_interval_seconds=120,
                    timeout_seconds=3,
                    retry_count=2,
                    remediation_profile="host-basic",
                    execution_target="local:system-network",
                    is_enabled=False,
                ),
            ]
        )

    db.commit()
