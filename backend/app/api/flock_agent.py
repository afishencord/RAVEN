from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db
from app.models import FlockTask, utcnow
from app.schemas import (
    FlockClaimedTaskRead,
    FlockDispatchRequest,
    FlockDispatchResponse,
    FlockEnrollmentRequest,
    FlockEnrollmentResponse,
    FlockHeartbeatRequest,
    FlockHeartbeatResponse,
    FlockTaskResultRequest,
)
from app.services.flock import (
    authenticate_agent,
    create_agent,
    default_policy,
    find_enrollment_token,
    mark_agent_seen,
    resolve_agent_target,
    serialize_policy,
    wait_for_task_result,
)

router = APIRouter(prefix="/flock", tags=["flock-agent"])


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def _require_internal_token(x_flock_internal_token: str | None) -> None:
    expected = get_settings().flock_internal_token
    if not expected or x_flock_internal_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Flock internal token")


@router.post("/enroll", response_model=FlockEnrollmentResponse)
def enroll(payload: FlockEnrollmentRequest, db: Session = Depends(get_db)):
    enrollment_token = find_enrollment_token(db, payload.enrollment_token)
    if not enrollment_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid enrollment token")
    agent, agent_token = create_agent(
        db,
        name=payload.name,
        hostname=payload.hostname,
        platform=payload.platform,
        architecture=payload.architecture,
        version=payload.version,
        metadata_json=payload.metadata_json,
        enrollment_token=enrollment_token,
    )
    policy = agent.policy or default_policy(db)
    db.commit()
    db.refresh(agent)
    return FlockEnrollmentResponse(agent_id=agent.agent_id, agent_token=agent_token, policy=serialize_policy(db, policy))


@router.post("/agents/{agent_id}/heartbeat", response_model=FlockHeartbeatResponse)
def heartbeat(
    agent_id: str,
    payload: FlockHeartbeatRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent = authenticate_agent(db, agent_id, _bearer_token(authorization))
    if payload.hostname:
        agent.hostname = payload.hostname
    if payload.platform:
        agent.platform = payload.platform
    if payload.architecture:
        agent.architecture = payload.architecture
    if payload.version:
        agent.version = payload.version
    agent.metadata_json = {**(agent.metadata_json or {}), **payload.metadata_json}
    mark_agent_seen(db, agent)
    policy = agent.policy or default_policy(db)
    db.commit()
    return FlockHeartbeatResponse(status="ok", policy=serialize_policy(db, policy))


@router.post("/agents/{agent_id}/tasks/claim", response_model=FlockClaimedTaskRead | None)
def claim_task(agent_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    agent = authenticate_agent(db, agent_id, _bearer_token(authorization))
    mark_agent_seen(db, agent)
    task = (
        db.query(FlockTask)
        .filter(FlockTask.agent_id == agent.id, FlockTask.status == "queued")
        .order_by(FlockTask.queued_at.asc(), FlockTask.id.asc())
        .first()
    )
    if not task:
        db.commit()
        return None
    task.status = "running"
    task.claimed_at = utcnow()
    db.commit()
    db.refresh(task)
    return FlockClaimedTaskRead(id=task.id, command=task.command, timeout_seconds=task.timeout_seconds)


@router.post("/agents/{agent_id}/tasks/{task_id}/result")
def submit_task_result(
    agent_id: str,
    task_id: int,
    payload: FlockTaskResultRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent = authenticate_agent(db, agent_id, _bearer_token(authorization))
    task = db.query(FlockTask).filter(FlockTask.id == task_id, FlockTask.agent_id == agent.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Flock task not found")
    mark_agent_seen(db, agent)
    task.exit_code = payload.exit_code
    task.output = payload.output[:8000]
    task.status = "success" if payload.exit_code == 0 else "failed"
    task.finished_at = utcnow()
    db.commit()
    return {"status": "ok"}


@router.post("/internal/dispatch", response_model=FlockDispatchResponse)
def dispatch_task(
    payload: FlockDispatchRequest,
    x_flock_internal_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_internal_token(x_flock_internal_token)
    agent = resolve_agent_target(db, payload.target)
    if not agent:
        return FlockDispatchResponse(status="failed", exit_code=1, output=f"No enrolled Flock agent matches target {payload.target!r}.")
    policy = agent.policy or default_policy(db)
    timeout_seconds = max(1, min(payload.timeout_seconds or policy.task_timeout_seconds, policy.task_timeout_seconds))
    task = FlockTask(
        agent_id=agent.id,
        execution_task_id=payload.execution_task_id,
        command=payload.command,
        timeout_seconds=timeout_seconds,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    finished = wait_for_task_result(db, task, timeout_seconds=timeout_seconds + 10, poll_seconds=get_settings().flock_result_poll_seconds)
    return FlockDispatchResponse(
        status=finished.status,
        exit_code=finished.exit_code if finished.exit_code is not None else 1,
        output=finished.output or "",
        agent_id=agent.agent_id,
        task_id=finished.id,
    )
