from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import AIRecommendation, ApprovalDecision, ExecutionTask, Incident, IncidentNote, Node, User
from app.schemas import MessageIncidentRead

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=list[MessageIncidentRead])
def list_messages(
    archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Incident)
    query = query.filter(Incident.archived_at.isnot(None) if archived else Incident.archived_at.is_(None))
    incidents = query.order_by(desc(Incident.started_at), desc(Incident.id)).limit(50).all()
    response: list[MessageIncidentRead] = []
    for incident in incidents:
        recommendations = (
            db.query(AIRecommendation)
            .filter(AIRecommendation.incident_id == incident.id)
            .order_by(AIRecommendation.created_at.asc(), AIRecommendation.id.asc())
            .all()
        )
        latest_recommendation = recommendations[-1] if recommendations else None
        notes = (
            db.query(IncidentNote)
            .filter(IncidentNote.incident_id == incident.id)
            .order_by(desc(IncidentNote.created_at), desc(IncidentNote.id))
            .all()
        )
        executions = (
            db.query(ExecutionTask)
            .filter(ExecutionTask.incident_id == incident.id)
            .order_by(desc(ExecutionTask.queued_at), desc(ExecutionTask.id))
            .all()
        )
        approvals = (
            db.query(ApprovalDecision)
            .filter(ApprovalDecision.incident_id == incident.id)
            .order_by(desc(ApprovalDecision.decided_at), desc(ApprovalDecision.id))
            .all()
        )
        node = db.query(Node).filter(Node.id == incident.node_id).first()
        if node:
            response.append(
                MessageIncidentRead(
                    incident=incident,
                    node=node,
                    latest_recommendation=latest_recommendation,
                    recommendations=recommendations,
                    notes=notes,
                    executions=executions,
                    approvals=approvals,
                )
            )
    return response
