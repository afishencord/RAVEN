from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_admin, require_operator_or_admin
from app.models import AIRecommendation, ApprovalDecision, Credential, ExecutionTask, HealthCheckResult, Incident, Node, NodeHealthCheck, User
from app.schemas import NodeCreate, NodeDetailRead, NodeHealthCheckCreate, NodeHealthCheckRead, NodeHealthCheckReplaceRequest, NodeRead, NodeUpdate
from app.services.health_checks import run_health_check
from app.services.incident_workflow import ensure_default_health_checks, process_health_result, run_and_record_health_check, write_audit_log

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
    node_data = payload.model_dump()
    node_data["remediation_profile"] = "command-executor"
    node = Node(**node_data)
    db.add(node)
    db.flush()
    ensure_default_health_checks(db, node)
    db.commit()
    db.refresh(node)
    write_audit_log(db, actor=current_user, entity_type="node", entity_id=str(node.id), action="created", details=payload.model_dump())
    db.commit()
    return node


@router.get("/{node_id}/health-checks", response_model=list[NodeHealthCheckRead])
def list_node_health_checks(node_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    checks = ensure_default_health_checks(db, node)
    db.commit()
    return checks


@router.put("/{node_id}/health-checks", response_model=list[NodeHealthCheckRead])
def replace_node_health_checks(node_id: int, payload: NodeHealthCheckReplaceRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    for existing in db.query(NodeHealthCheck).filter(NodeHealthCheck.node_id == node.id).all():
        db.delete(existing)
    db.flush()
    checks: list[NodeHealthCheck] = []
    for index, item in enumerate(payload.health_checks):
        check = NodeHealthCheck(
            node_id=node.id,
            name=item.name,
            check_type=item.check_type,
            config_json=item.config_json,
            interval_seconds=item.interval_seconds,
            timeout_seconds=item.timeout_seconds,
            retry_count=item.retry_count,
            is_enabled=item.is_enabled,
            sort_order=item.sort_order if item.sort_order is not None else index,
        )
        db.add(check)
        checks.append(check)
    if checks:
        first = checks[0]
        node.health_check_type = first.check_type
        node.check_interval_seconds = first.interval_seconds
        node.timeout_seconds = first.timeout_seconds
        node.retry_count = first.retry_count
        node.url = first.config_json.get("url") or node.url
        node.health_check_path = first.config_json.get("path") or first.config_json.get("health_path") or node.health_check_path
        node.expected_status_code = int(first.config_json.get("expected_status_code") or node.expected_status_code)
        node.expected_response_contains = first.config_json.get("expected_response_contains") or node.expected_response_contains
    else:
        checks = ensure_default_health_checks(db, node)
    db.commit()
    write_audit_log(db, actor=current_user, entity_type="node", entity_id=str(node.id), action="health_checks_updated", details={"count": len(checks)})
    db.commit()
    return (
        db.query(NodeHealthCheck)
        .filter(NodeHealthCheck.node_id == node.id)
        .order_by(NodeHealthCheck.sort_order.asc(), NodeHealthCheck.id.asc())
        .all()
    )


@router.post("/{node_id}/health-checks/{check_id}/run")
def run_node_health_check(node_id: int, check_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    check = db.query(NodeHealthCheck).filter(NodeHealthCheck.id == check_id, NodeHealthCheck.node_id == node.id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Health check not found")
    result = run_health_check(node, check, db=db)
    row = process_health_result(db, node, result, actor=current_user, health_check=check)
    db.commit()
    return {"status": row.status, "checked_at": row.checked_at, "check_id": check.id}


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
    if not node.remediation_profile:
        node.remediation_profile = "command-executor"
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
    incidents = db.query(Incident).filter(Incident.node_id == node.id).order_by(desc(Incident.started_at)).limit(20).all()
    recommendations = (
        db.query(AIRecommendation)
        .filter(AIRecommendation.node_id == node.id)
        .order_by(desc(AIRecommendation.created_at), desc(AIRecommendation.id))
        .limit(20)
        .all()
    )
    health_checks = db.query(HealthCheckResult).filter(HealthCheckResult.node_id == node.id).order_by(desc(HealthCheckResult.checked_at)).limit(30).all()
    health_check_definitions = (
        db.query(NodeHealthCheck)
        .filter(NodeHealthCheck.node_id == node.id)
        .order_by(NodeHealthCheck.sort_order.asc(), NodeHealthCheck.id.asc())
        .all()
    )
    if not health_check_definitions:
        health_check_definitions = ensure_default_health_checks(db, node)
        db.commit()
    executions = (
        db.query(ExecutionTask)
        .filter(ExecutionTask.node_id == node.id)
        .order_by(desc(ExecutionTask.queued_at), desc(ExecutionTask.id))
        .limit(20)
        .all()
    )
    approvals = (
        db.query(ApprovalDecision)
        .join(Incident, Incident.id == ApprovalDecision.incident_id)
        .filter(Incident.node_id == node.id)
        .order_by(desc(ApprovalDecision.decided_at))
        .limit(20)
        .all()
    )
    credential = db.query(Credential).filter(Credential.id == node.credential_id).first() if node.credential_id else None
    return NodeDetailRead(
        node=node,
        health_checks=health_checks,
        health_check_definitions=health_check_definitions,
        incidents=incidents,
        recommendations=recommendations,
        executions=executions,
        approvals=approvals,
        credential=credential and {
            "id": credential.id,
            "name": credential.name,
            "kind": credential.kind,
            "username": credential.username,
            "description": credential.description,
            "metadata_json": credential.metadata_json,
            "has_secret": bool(credential.secret_value),
            "masked_secret": "*" * 8 if credential.secret_value else "",
            "created_at": credential.created_at,
            "updated_at": credential.updated_at,
        },
    )
