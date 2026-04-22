from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import AIRecommendation, ApprovalDecision, ExecutionTask, Incident, IncidentNote, Node, User
from app.schemas import MessageIncidentRead

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=list[MessageIncidentRead])
def list_messages(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    incidents = db.query(Incident).order_by(desc(Incident.started_at), desc(Incident.id)).limit(50).all()
    response: list[MessageIncidentRead] = []
    for incident in incidents:
        latest_recommendation = (
            db.query(AIRecommendation)
            .filter(AIRecommendation.incident_id == incident.id)
            .order_by(desc(AIRecommendation.created_at), desc(AIRecommendation.id))
            .first()
        )
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
                    notes=notes,
                    executions=executions,
                    approvals=approvals,
                )
            )
    return response
