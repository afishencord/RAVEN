from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_admin, require_operator_or_admin
from app.models import AIRecommendation, ApprovalDecision, ExecutionTask, HealthCheckResult, Incident, Node, RemediationProfile, User
from app.schemas import NodeCreate, NodeDetailRead, NodeRead, NodeUpdate
from app.services.incident_workflow import run_and_record_health_check, write_audit_log

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeRead])
def list_nodes(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Node)
    if status_filter == "disabled":
        query = query.filter(Node.is_enabled.is_(False))
    elif status_filter:
        query = query.filter(Node.current_status == status_filter, Node.is_enabled.is_(True))
    return query.order_by(Node.environment.asc(), Node.name.asc()).all()


@router.post("", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    node = Node(**payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    write_audit_log(db, actor=current_user, entity_type="node", entity_id=str(node.id), action="created", details=payload.model_dump())
    db.commit()
    return node


@router.get("/{node_id}", response_model=NodeRead)
def get_node(node_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.put("/{node_id}", response_model=NodeRead)
def update_node(node_id: int, payload: NodeUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    db.commit()
    db.refresh(node)
    write_audit_log(db, actor=current_user, entity_type="node", entity_id=str(node.id), action="updated", details=payload.model_dump(exclude_unset=True))
    db.commit()
    return node


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    db.delete(node)
    write_audit_log(db, actor=current_user, entity_type="node", entity_id=str(node.id), action="deleted", details={})
    db.commit()


@router.post("/{node_id}/rerun-check")
def rerun_check(node_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    row = run_and_record_health_check(db, node, actor=current_user)
    return {"status": row.status, "checked_at": row.checked_at}


@router.get("/{node_id}/detail", response_model=NodeDetailRead)
def get_node_detail(node_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    profile = db.query(RemediationProfile).filter(RemediationProfile.name == node.remediation_profile).first()
    incidents = db.query(Incident).filter(Incident.node_id == node.id).order_by(desc(Incident.started_at)).limit(20).all()
    recommendations = db.query(AIRecommendation).filter(AIRecommendation.node_id == node.id).order_by(desc(AIRecommendation.created_at)).limit(20).all()
    health_checks = db.query(HealthCheckResult).filter(HealthCheckResult.node_id == node.id).order_by(desc(HealthCheckResult.checked_at)).limit(30).all()
    executions = db.query(ExecutionTask).filter(ExecutionTask.node_id == node.id).order_by(desc(ExecutionTask.queued_at)).limit(20).all()
    approvals = (
        db.query(ApprovalDecision)
        .join(Incident, Incident.id == ApprovalDecision.incident_id)
        .filter(Incident.node_id == node.id)
        .order_by(desc(ApprovalDecision.decided_at))
        .limit(20)
        .all()
    )
    return NodeDetailRead(
        node=node,
        health_checks=health_checks,
        incidents=incidents,
        recommendations=recommendations,
        executions=executions,
        approvals=approvals,
        remediation_profile=profile,
    )
