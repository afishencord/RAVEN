from __future__ import annotations

import secrets
import time
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.database import SessionLocal
from app.models import FlockAgent, FlockEnrollmentToken, FlockMetric, FlockPolicy, FlockTask, Node, NodeHealthCheck, utcnow
from app.schemas import FlockAgentRead, FlockPolicyRead


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def default_policy(db: Session) -> FlockPolicy:
    policy = (
        db.query(FlockPolicy)
        .filter(FlockPolicy.is_default.is_(True), FlockPolicy.is_enabled.is_(True))
        .order_by(FlockPolicy.id.asc())
        .first()
    )
    if policy:
        return policy
    policy = db.query(FlockPolicy).filter(FlockPolicy.is_enabled.is_(True)).order_by(FlockPolicy.id.asc()).first()
    if policy:
        return policy
    policy = FlockPolicy(name="Default Linux/Unix Policy", is_default=True)
    db.add(policy)
    db.flush()
    return policy


def serialize_policy(db: Session, policy: FlockPolicy) -> FlockPolicyRead:
    agent_count = db.query(func.count(FlockAgent.id)).filter(FlockAgent.policy_id == policy.id, FlockAgent.status != "unenrolled").scalar() or 0
    return FlockPolicyRead(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        is_default=policy.is_default,
        is_enabled=policy.is_enabled,
        heartbeat_interval_seconds=policy.heartbeat_interval_seconds,
        task_timeout_seconds=policy.task_timeout_seconds,
        command_allowlist=policy.command_allowlist or [],
        agent_count=agent_count,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def serialize_agent(db: Session, agent: FlockAgent) -> FlockAgentRead:
    pending_count = db.query(func.count(FlockTask.id)).filter(FlockTask.agent_id == agent.id, FlockTask.status == "queued").scalar() or 0
    latest_metric = db.query(FlockMetric).filter(FlockMetric.agent_id == agent.id).order_by(FlockMetric.collected_at.desc()).first()
    return FlockAgentRead(
        id=agent.id,
        agent_id=agent.agent_id,
        name=agent.name,
        hostname=agent.hostname,
        platform=agent.platform,
        architecture=agent.architecture,
        version=agent.version,
        policy_id=agent.policy_id,
        policy_name=agent.policy.name if agent.policy else None,
        enrollment_token_id=agent.enrollment_token_id,
        node_id=agent.node_id,
        status=agent.status,
        last_seen_at=agent.last_seen_at,
        enrolled_at=agent.enrolled_at,
        unenrolled_at=agent.unenrolled_at,
        metadata_json=agent.metadata_json or {},
        latest_metrics=latest_metric.payload_json if latest_metric else None,
        pending_task_count=pending_count,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def find_enrollment_token(db: Session, token_value: str) -> FlockEnrollmentToken | None:
    tokens = db.query(FlockEnrollmentToken).filter(FlockEnrollmentToken.is_enabled.is_(True)).all()
    for token in tokens:
        if verify_password(token_value, token.token_hash):
            return token
    return None


def authenticate_agent(db: Session, agent_id: str, bearer_token: str) -> FlockAgent:
    agent = db.query(FlockAgent).filter(FlockAgent.agent_id == agent_id).first()
    if not agent or not verify_password(bearer_token, agent.token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials")
    if agent.status == "unenrolled":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Flock agent is unenrolled")
    return agent


def mark_agent_seen(db: Session, agent: FlockAgent) -> None:
    agent.last_seen_at = utcnow()
    if agent.status != "unenroll_pending":
        agent.status = "online"


def sync_inventory_node(db: Session, agent: FlockAgent) -> Node:
    node = db.query(Node).filter(Node.id == agent.node_id).first() if agent.node_id else None
    if not node:
        node = db.query(Node).filter(Node.execution_target == f"flock:{agent.agent_id}").first()
    if not node:
        node = Node(
            name=agent.name,
            description="Auto-enrolled Flock agent host.",
            environment=str((agent.metadata_json or {}).get("environment") or "prod"),
            host=agent.hostname,
            health_check_type="ping",
            health_check_path=None,
            expected_status_code=200,
            check_interval_seconds=60,
            timeout_seconds=5,
            retry_count=3,
            remediation_profile="command-executor",
            execution_mode="agent",
            execution_target=f"flock:{agent.agent_id}",
            context_text=f"Linux/Unix host enrolled through Flock agent {agent.name}.",
            approved_command_policy="Use sudo-backed diagnostics and targeted remediation commands only.",
            current_status="healthy",
            is_enabled=True,
        )
        db.add(node)
        db.flush()
    else:
        node.name = agent.name
        node.host = agent.hostname
        node.execution_mode = "agent"
        node.execution_target = f"flock:{agent.agent_id}"
        node.is_enabled = True
    agent.node_id = node.id
    _ensure_agent_health_checks(db, node)
    return node


def _ensure_agent_health_checks(db: Session, node: Node) -> None:
    existing = db.query(NodeHealthCheck).filter(NodeHealthCheck.node_id == node.id).all()
    if existing:
        return
    checks = [
        NodeHealthCheck(node_id=node.id, name="Ping reachability", check_type="ping", config_json={}, interval_seconds=60, timeout_seconds=5, retry_count=3, sort_order=0),
        NodeHealthCheck(node_id=node.id, name="Memory usage", check_type="memory", config_json={"warning_percent": 80, "critical_percent": 90}, interval_seconds=60, timeout_seconds=5, retry_count=3, sort_order=1),
        NodeHealthCheck(node_id=node.id, name="Disk usage", check_type="disk", config_json={"path": "/", "warning_percent": 80, "critical_percent": 90}, interval_seconds=120, timeout_seconds=5, retry_count=3, sort_order=2),
        NodeHealthCheck(node_id=node.id, name="Network drops", check_type="network", config_json={"drop_threshold": 0}, interval_seconds=120, timeout_seconds=5, retry_count=3, sort_order=3),
    ]
    for check in checks:
        db.add(check)


def create_agent(
    db: Session,
    *,
    name: str,
    hostname: str,
    platform: str,
    architecture: str,
    version: str,
    metadata_json: dict,
    enrollment_token: FlockEnrollmentToken,
) -> tuple[FlockAgent, str]:
    agent_token = generate_token()
    policy = enrollment_token.policy or default_policy(db)
    agent = (
        db.query(FlockAgent)
        .filter(FlockAgent.name == name, FlockAgent.hostname == hostname)
        .order_by(FlockAgent.id.desc())
        .first()
    )
    if not agent:
        agent = FlockAgent(agent_id=secrets.token_hex(12), name=name, hostname=hostname)
        db.add(agent)
    agent.agent_id = secrets.token_hex(12)
    agent.name = name
    agent.hostname = hostname
    agent.platform = platform
    agent.architecture = architecture
    agent.version = version
    agent.token_hash = get_password_hash(agent_token)
    agent.policy_id = policy.id
    agent.enrollment_token_id = enrollment_token.id
    agent.status = "online"
    agent.last_seen_at = utcnow()
    agent.enrolled_at = utcnow()
    agent.unenrolled_at = None
    agent.metadata_json = metadata_json
    enrollment_token.last_used_at = utcnow()
    db.flush()
    sync_inventory_node(db, agent)
    return agent, agent_token


def cleanup_agent_inventory(db: Session, agent: FlockAgent) -> None:
    node = db.query(Node).filter(Node.id == agent.node_id).first() if agent.node_id else None
    db.query(FlockMetric).filter(FlockMetric.agent_id == agent.id).delete(synchronize_session=False)
    db.query(FlockTask).filter(FlockTask.agent_id == agent.id).delete(synchronize_session=False)
    if node:
        db.delete(node)
    db.delete(agent)


def mark_agent_unenrolled(db: Session, agent: FlockAgent) -> None:
    agent.status = "unenrolled"
    agent.unenrolled_at = utcnow()
    if agent.node_id:
        node = db.query(Node).filter(Node.id == agent.node_id).first()
        if node:
            node.is_enabled = False
            node.current_status = "disabled"


def cleanup_agent_inventory_by_id(agent_id: int) -> None:
    cleanup_db = SessionLocal()
    try:
        agent = cleanup_db.query(FlockAgent).filter(FlockAgent.id == agent_id).first()
        if agent:
            cleanup_agent_inventory(cleanup_db, agent)
            cleanup_db.commit()
    finally:
        cleanup_db.close()


def resolve_agent_target(db: Session, target: str) -> FlockAgent | None:
    normalized = target.removeprefix("flock:").strip()
    if not normalized:
        return None
    query = db.query(FlockAgent).filter(FlockAgent.status != "unenrolled")
    if normalized.isdigit():
        agent = query.filter(FlockAgent.id == int(normalized)).first()
        if agent:
            return agent
    return query.filter((FlockAgent.agent_id == normalized) | (FlockAgent.name == normalized) | (FlockAgent.hostname == normalized)).first()


def wait_for_task_result(db: Session, task: FlockTask, timeout_seconds: int, poll_seconds: int) -> FlockTask:
    deadline = utcnow() + timedelta(seconds=timeout_seconds)
    while utcnow() < deadline:
        db.refresh(task)
        if task.status in {"success", "failed"}:
            return task
        time.sleep(max(1, poll_seconds))
    task.status = "failed"
    task.finished_at = utcnow()
    task.exit_code = 124
    task.output = f"Flock task timed out after {timeout_seconds} seconds."
    db.commit()
    db.refresh(task)
    return task
