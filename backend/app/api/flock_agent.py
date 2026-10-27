from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db
from app.models import FlockMetric, FlockTask, utcnow
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
    cleanup_agent_inventory_by_id,
    create_agent,
    find_enrollment_token,
    mark_agent_seen,
    mark_agent_unenrolled,
    resolve_agent_target,
    serialize_policy,
    sync_inventory_node,
    wait_for_task_result,
)
from app.services.flock_identity import identity_key
from app.services.flock_policy import FlockPolicyError, authorize_command, policy_timeout

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
def enroll(
    payload: FlockEnrollmentRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
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
        existing_agent_id=payload.existing_agent_id,
        existing_agent_token=_bearer_token(authorization) if authorization is not None else None,
    )
    policy = agent.policy
    db.commit()
    db.refresh(agent)
    return FlockEnrollmentResponse(agent_id=agent.agent_id, agent_token=agent_token, policy=serialize_policy(db, policy) if policy else None)


@router.post("/agents/{agent_id}/heartbeat", response_model=FlockHeartbeatResponse)
def heartbeat(
    agent_id: str,
    payload: FlockHeartbeatRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent = authenticate_agent(db, agent_id, _bearer_token(authorization))
    if payload.hostname is not None:
        try:
            matches = identity_key(payload.hostname, hostname=True) == agent.hostname_key
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not matches:
            raise HTTPException(status_code=409, detail="Heartbeat cannot change the enrolled hostname; administrator recovery is required")
    if payload.platform:
        agent.platform = payload.platform
    if payload.architecture:
        agent.architecture = payload.architecture
    if payload.version:
        agent.version = payload.version
    agent.metadata_json = {**(agent.metadata_json or {}), **payload.metadata_json}
    mark_agent_seen(db, agent)
    if payload.metrics_json:
        db.add(FlockMetric(agent_id=agent.id, payload_json=payload.metrics_json))
    if not agent.node_id:
        sync_inventory_node(db, agent)
    policy = agent.policy
    db.commit()
    return FlockHeartbeatResponse(status="ok", policy=serialize_policy(db, policy) if policy else None)


@router.post("/agents/{agent_id}/tasks/claim", response_model=FlockClaimedTaskRead | None)
def claim_task(agent_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    agent = authenticate_agent(db, agent_id, _bearer_token(authorization))
    mark_agent_seen(db, agent)
    task = (
        db.query(FlockTask)
        .filter(
            FlockTask.agent_id == agent.id,
            (FlockTask.status == "queued") | ((FlockTask.task_type == "unenroll") & (FlockTask.status == "running")),
        )
        .order_by(FlockTask.queued_at.asc(), FlockTask.id.asc())
        .first()
    )
    if not task:
        db.commit()
        return None
    if task.task_type != "unenroll":
        try:
            if task.task_type != "command" or agent.status == "unenroll_pending":
                raise FlockPolicyError("Command execution is unavailable for this agent/task")
            authorize_command(agent.policy, task.command)
            task.timeout_seconds = max(1, min(task.timeout_seconds, policy_timeout(agent.policy)))
        except FlockPolicyError as exc:
            task.status = "failed"
            task.finished_at = utcnow()
            task.exit_code = 126
            task.output = f"Flock policy denied queued task: {exc}"
            db.commit()
            return None
    task.status = "running"
    task.claimed_at = utcnow()
    db.commit()
    db.refresh(task)
    return FlockClaimedTaskRead(
        id=task.id, task_type=task.task_type, command=task.command, timeout_seconds=task.timeout_seconds,
        policy=serialize_policy(db, agent.policy) if agent.policy else None,
    )


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
    if task.task_type == "unenroll" and payload.exit_code == 0:
        cleanup_agent_id = agent.id
        mark_agent_unenrolled(db, agent)
    db.commit()
    if task.task_type == "unenroll" and payload.exit_code == 0:
        cleanup_agent_inventory_by_id(cleanup_agent_id)
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
    policy = agent.policy
    try:
        if agent.status == "unenroll_pending":
            raise FlockPolicyError("Flock agent unenrollment is pending")
        authorize_command(policy, payload.command)
        timeout_seconds = max(1, min(payload.timeout_seconds, policy_timeout(policy)))
    except FlockPolicyError as exc:
        return FlockDispatchResponse(status="failed", exit_code=126, output=f"Flock policy denied command: {exc}", agent_id=agent.agent_id)
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
