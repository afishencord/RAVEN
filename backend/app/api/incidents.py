from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_operator_or_admin
from app.models import AIRecommendation, Incident, IncidentNote, User, utcnow
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
    payload = ai_service.generate(node=node, incident=incident, recent_history=[], prior_incidents=[])
    recommendation = ai_service.persist(incident=incident, node=node, payload=payload)
    db.add(recommendation)
    write_audit_log(db, actor=current_user, entity_type="incident", entity_id=str(incident.id), action="recommendation_refreshed", details={})
    db.commit()
    return StatusResponse(status="refreshed")


@router.post("/{incident_id}/approve", response_model=StatusResponse)
def approve_remediation(
    incident_id: int,
    payload: IncidentActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator_or_admin),
):
    incident = _get_incident_or_404(db, incident_id)
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
