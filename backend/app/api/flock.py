from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models import FlockAgent, FlockMetric, FlockPolicy, FlockTask, User, utcnow
from app.schemas import FlockAgentRead, FlockAgentUpdate, FlockMetricRead, FlockPolicyCreate, FlockPolicyRead, FlockPolicyUpdate, FlockUnenrollResponse
from app.services.flock import serialize_agent, serialize_policy

router = APIRouter(prefix="/flock", tags=["flock"])


def _clear_default_policy(db: Session, policy_id: int | None = None) -> None:
    query = db.query(FlockPolicy).filter(FlockPolicy.is_default.is_(True))
    if policy_id is not None:
        query = query.filter(FlockPolicy.id != policy_id)
    for policy in query.all():
        policy.is_default = False


@router.get("/agents", response_model=list[FlockAgentRead])
def list_agents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    agents = db.query(FlockAgent).filter(FlockAgent.status != "unenrolled").order_by(FlockAgent.last_seen_at.desc().nullslast(), FlockAgent.name.asc()).all()
    return [serialize_agent(db, agent) for agent in agents]


@router.put("/agents/{agent_id}", response_model=FlockAgentRead)
def update_agent(agent_id: int, payload: FlockAgentUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    agent = db.query(FlockAgent).filter(FlockAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Flock agent not found")
    values = payload.model_dump(exclude_unset=True)
    if "policy_id" in values and values["policy_id"] is not None:
        policy = db.query(FlockPolicy).filter(FlockPolicy.id == values["policy_id"]).first()
        if not policy:
            raise HTTPException(status_code=404, detail="Flock policy not found")
    for key, value in values.items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return serialize_agent(db, agent)


@router.post("/agents/{agent_id}/unenroll", response_model=FlockUnenrollResponse)
def unenroll_agent(agent_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    agent = db.query(FlockAgent).filter(FlockAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Flock agent not found")
    if agent.status == "unenrolled":
        return FlockUnenrollResponse(status=agent.status, agent_id=agent.agent_id, node_id=agent.node_id, task_id=None)
    existing = (
        db.query(FlockTask)
        .filter(FlockTask.agent_id == agent.id, FlockTask.task_type == "unenroll", FlockTask.status.in_(["queued", "running"]))
        .order_by(FlockTask.id.desc())
        .first()
    )
    task = existing
    if not task:
        task = FlockTask(
            agent_id=agent.id,
            task_type="unenroll",
            command="__flock_unenroll__",
            timeout_seconds=30,
        )
        db.add(task)
        db.flush()
    agent.status = "unenroll_pending"
    agent.updated_at = utcnow()
    db.commit()
    return FlockUnenrollResponse(status=agent.status, agent_id=agent.agent_id, node_id=agent.node_id, task_id=task.id)


@router.get("/agents/{agent_id}/metrics", response_model=list[FlockMetricRead])
def list_agent_metrics(agent_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    agent = db.query(FlockAgent).filter(FlockAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Flock agent not found")
    return db.query(FlockMetric).filter(FlockMetric.agent_id == agent.id).order_by(desc(FlockMetric.collected_at)).limit(50).all()


@router.get("/policies", response_model=list[FlockPolicyRead])
def list_policies(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    policies = db.query(FlockPolicy).order_by(FlockPolicy.is_default.desc(), FlockPolicy.name.asc()).all()
    return [serialize_policy(db, policy) for policy in policies]


@router.post("/policies", response_model=FlockPolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(payload: FlockPolicyCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if payload.is_default:
        _clear_default_policy(db)
    policy = FlockPolicy(**payload.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return serialize_policy(db, policy)


@router.put("/policies/{policy_id}", response_model=FlockPolicyRead)
def update_policy(policy_id: int, payload: FlockPolicyUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    policy = db.query(FlockPolicy).filter(FlockPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Flock policy not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("is_default"):
        _clear_default_policy(db, policy_id=policy.id)
    for key, value in values.items():
        setattr(policy, key, value)
    db.commit()
    db.refresh(policy)
    return serialize_policy(db, policy)
