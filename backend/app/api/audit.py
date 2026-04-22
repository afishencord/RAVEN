from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import ApprovalDecision, AuditLog, User
from app.schemas import ApprovalDecisionRead, AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogRead])
def list_audit_logs(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    return query.order_by(desc(AuditLog.created_at)).limit(200).all()


@router.get("/approvals", response_model=list[ApprovalDecisionRead])
def list_approval_decisions(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(ApprovalDecision).order_by(desc(ApprovalDecision.decided_at)).limit(200).all()
