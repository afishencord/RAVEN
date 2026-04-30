from __future__ import annotations

import secrets
import time
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.models import FlockAgent, FlockEnrollmentToken, FlockPolicy, FlockTask, utcnow
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
    agent_count = db.query(func.count(FlockAgent.id)).filter(FlockAgent.policy_id == policy.id).scalar() or 0
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
        status=agent.status,
        last_seen_at=agent.last_seen_at,
        enrolled_at=agent.enrolled_at,
        metadata_json=agent.metadata_json or {},
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
    return agent


def mark_agent_seen(db: Session, agent: FlockAgent) -> None:
    agent.last_seen_at = utcnow()
    agent.status = "online"


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
    agent = FlockAgent(
        agent_id=secrets.token_hex(12),
        name=name,
        hostname=hostname,
        platform=platform,
        architecture=architecture,
        version=version,
        token_hash=get_password_hash(agent_token),
        policy_id=policy.id,
        enrollment_token_id=enrollment_token.id,
        status="online",
        last_seen_at=utcnow(),
        metadata_json=metadata_json,
    )
    enrollment_token.last_used_at = utcnow()
    db.add(agent)
    db.flush()
    return agent, agent_token


def resolve_agent_target(db: Session, target: str) -> FlockAgent | None:
    normalized = target.removeprefix("flock:").strip()
    if not normalized:
        return None
    query = db.query(FlockAgent)
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
