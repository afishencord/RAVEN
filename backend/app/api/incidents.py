from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_operator_or_admin
from app.models import AIRecommendation, ExecutionTask, HealthCheckResult, Incident, IncidentNote, User, utcnow
from app.schemas import IncidentActionRequest, IncidentNoteCreate, IncidentNoteRead, IncidentRead, StatusResponse
from app.services.ai_service import AIRecommendationService
from app.services.execution_runner import queue_execution, reject_execution
from app.services.incident_workflow import write_audit_log

router = APIRouter(prefix="/incidents", tags=["incidents"])
ai_service = AIRecommendationService()


def _get_incident_or_404(db: Session, incident_id: int) -> Incident:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


def _recommendation_context(db: Session, incident: Incident) -> tuple[list[dict], list[dict]]:
    recent_history = [
        {
            "kind": "health_check",
            "status": check.status,
            "success": check.success,
            "http_status": check.http_status,
            "error_type": check.error_type,
            "error_detail": check.error_detail,
            "checked_at": check.checked_at.isoformat(),
        }
        for check in (
            db.query(HealthCheckResult)
            .filter(HealthCheckResult.node_id == incident.node_id)
            .order_by(desc(HealthCheckResult.checked_at))
            .limit(10)
            .all()
        )
    ]
    executions = (
        db.query(ExecutionTask)
        .filter(ExecutionTask.incident_id == incident.id)
        .order_by(desc(ExecutionTask.queued_at), desc(ExecutionTask.id))
        .limit(8)
        .all()
    )
    recent_history.extend(ai_service.latest_execution_context(incident.node, executions))
    prior_incidents = [
        {
            "failure_type": item.failure_type,
            "summary": item.summary,
            "started_at": item.started_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }
        for item in (
            db.query(Incident)
            .filter(Incident.node_id == incident.node_id, Incident.id != incident.id)
            .order_by(desc(Incident.started_at))
            .limit(5)
            .all()
        )
    ]
    return recent_history, prior_incidents


@router.get("", response_model=list[IncidentRead])
def list_incidents(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Incident).order_by(desc(Incident.started_at)).limit(100).all()


@router.post("/{incident_id}/acknowledge", response_model=StatusResponse)
def acknowledge_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    incident.status = "acknowledged"
    incident.acknowledged_at = utcnow()
    incident.acknowledged_by_id = current_user.id
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="acknowledged", details={})
    db.commit()
    return StatusResponse(status="acknowledged")


@router.post("/{incident_id}/archive", response_model=StatusResponse)
def archive_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    incident.archived_at = utcnow()
    incident.archived_by_id = current_user.id
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="archived", details={})
    db.commit()
    return StatusResponse(status="archived")


@router.post("/{incident_id}/unarchive", response_model=StatusResponse)
def unarchive_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    incident.archived_at = None
    incident.archived_by_id = None
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="unarchived", details={})
    db.commit()
    return StatusResponse(status="unarchived")


@router.post("/{incident_id}/close", response_model=StatusResponse)
def close_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    incident.status = "resolved"
    incident.is_active = False
    incident.resolved_at = incident.resolved_at or utcnow()
    incident.archived_at = utcnow()
    incident.archived_by_id = current_user.id
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="closed_archived", details={})
    db.commit()
    return StatusResponse(status="closed")


@router.post("/{incident_id}/notes", response_model=IncidentNoteRead)
def add_note(incident_id: int, payload: IncidentNoteCreate, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    note = IncidentNote(incident_id=incident.id, user_id=current_user.id, note=payload.note)
    db.add(note)
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="note_added", details={"note": payload.note})
    db.commit()
    db.refresh(note)
    return note


@router.post("/{incident_id}/recommendation/refresh", response_model=StatusResponse)
def refresh_recommendation(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    node = incident.node
    if not node:
        raise HTTPException(status_code=404, detail="Incident node not found")
    recent_history, prior_incidents = _recommendation_context(db, incident)
    payload = ai_service.generate(node=node, incident=incident, recent_history=recent_history, prior_incidents=prior_incidents)
    recommendation = ai_service.persist(incident=incident, node=node, payload=payload)
    db.add(recommendation)
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="recommendation_refreshed", details={})
    db.commit()
    return StatusResponse(status="refreshed")


@router.post("/{incident_id}/investigate-further", response_model=StatusResponse)
def investigate_further(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_operator_or_admin)):
    incident = _get_incident_or_404(db, incident_id)
    node = incident.node
    if not node:
        raise HTTPException(status_code=404, detail="Incident node not found")
    incident.status = "investigating"
    incident.archived_at = None
    incident.archived_by_id = None
    recent_history, prior_incidents = _recommendation_context(db, incident)
    recent_history.append(
        {
            "kind": "operator_intent",
            "intent": "investigate_further",
            "details": "Operator requested a root cause analysis workflow after apparent recovery.",
        }
    )
    payload = ai_service.generate(
        node=node,
        incident=incident,
        recent_history=recent_history,
        prior_incidents=prior_incidents,
        workflow_mode="root_cause",
    )
    recommendation = ai_service.persist(incident=incident, node=node, payload=payload)
    db.add(recommendation)
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="root_cause_investigation_started", details={})
    db.commit()
    return StatusResponse(status="investigating")


@router.post("/{incident_id}/approve", response_model=StatusResponse)
def approve_remediation(
    incident_id: int,
    payload: IncidentActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator_or_admin),
):
    incident = _get_incident_or_404(db, incident_id)
    if not payload.proposal_id:
        raise HTTPException(status_code=400, detail="proposal_id is required")
    recommendation = (
        db.query(AIRecommendation)
        .filter(AIRecommendation.incident_id == incident.id)
        .order_by(desc(AIRecommendation.created_at), desc(AIRecommendation.id))
        .first()
    )
    try:
        queue_execution(
            db,
            incident=incident,
            proposal_id=payload.proposal_id,
            approver=current_user,
            note=payload.note,
            recommendation_id=recommendation.id if recommendation else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StatusResponse(status="queued")


@router.post("/{incident_id}/reject", response_model=StatusResponse)
def reject_remediation(
    incident_id: int,
    payload: IncidentActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator_or_admin),
):
    incident = _get_incident_or_404(db, incident_id)
    if not payload.proposal_id:
        raise HTTPException(status_code=400, detail="proposal_id is required")
    recommendation = (
        db.query(AIRecommendation)
        .filter(AIRecommendation.incident_id == incident.id)
        .order_by(desc(AIRecommendation.created_at), desc(AIRecommendation.id))
        .first()
    )
    try:
        reject_execution(
            db,
            incident=incident,
            proposal_id=payload.proposal_id,
            actor=current_user,
            note=payload.note,
            recommendation_id=recommendation.id if recommendation else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StatusResponse(status="rejected")
