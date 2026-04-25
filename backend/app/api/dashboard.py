from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import ApprovalDecision, ExecutionTask, Incident, Node, User, utcnow
from app.schemas import DashboardMetricsRead, MetricBreakdownItem, TimeSeriesPoint

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _breakdown(rows: list[tuple[str | None, int]], fallback_label: str = "Unknown") -> list[MetricBreakdownItem]:
    return [
        MetricBreakdownItem(label=label or fallback_label, value=value)
        for label, value in rows
    ]


@router.get("/metrics", response_model=DashboardMetricsRead)
def get_dashboard_metrics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    now = utcnow()
    window_start = now.date() - timedelta(days=13)

    total_nodes = db.query(func.count(Node.id)).scalar() or 0
    enabled_nodes = db.query(func.count(Node.id)).filter(Node.is_enabled.is_(True)).scalar() or 0
    active_incidents = db.query(func.count(Incident.id)).filter(Incident.is_active.is_(True), Incident.archived_at.is_(None)).scalar() or 0
    resolved_incidents = db.query(func.count(Incident.id)).filter(Incident.resolved_at.isnot(None)).scalar() or 0
    successful_remediations = (
        db.query(func.count(ExecutionTask.id))
        .filter(ExecutionTask.status == "success", ExecutionTask.post_validation_status == "healthy")
        .scalar()
        or 0
    )

    resolved_rows = (
        db.query(Incident.started_at, Incident.resolved_at)
        .filter(Incident.resolved_at.isnot(None))
        .limit(500)
        .all()
    )
    resolution_durations = [
        (resolved_at - started_at).total_seconds() / 60
        for started_at, resolved_at in resolved_rows
        if started_at and resolved_at and resolved_at >= started_at
    ]
    average_resolution_minutes = round(sum(resolution_durations) / len(resolution_durations), 1) if resolution_durations else None

    enabled_state_rows = (
        db.query(Node.current_status, func.count(Node.id))
        .filter(Node.is_enabled.is_(True))
        .group_by(Node.current_status)
        .all()
    )
    disabled_nodes = db.query(func.count(Node.id)).filter(Node.is_enabled.is_(False)).scalar() or 0
    node_state_counts = _breakdown(enabled_state_rows)
    if disabled_nodes:
        node_state_counts.append(MetricBreakdownItem(label="disabled", value=disabled_nodes))

    successful_executions = (
        db.query(ExecutionTask.finished_at)
        .filter(
            ExecutionTask.status == "success",
            ExecutionTask.post_validation_status == "healthy",
            ExecutionTask.finished_at.isnot(None),
        )
        .all()
    )
    remediation_counts_by_day: dict[str, int] = {
        (window_start + timedelta(days=offset)).isoformat(): 0
        for offset in range(14)
    }
    for (finished_at,) in successful_executions:
        date_key = finished_at.date().isoformat()
        if date_key in remediation_counts_by_day:
            remediation_counts_by_day[date_key] += 1

    return DashboardMetricsRead(
        total_nodes=total_nodes,
        enabled_nodes=enabled_nodes,
        active_incidents=active_incidents,
        resolved_incidents=resolved_incidents,
        successful_remediations=successful_remediations,
        average_resolution_minutes=average_resolution_minutes,
        node_state_counts=node_state_counts,
        execution_status_counts=_breakdown(
            db.query(ExecutionTask.status, func.count(ExecutionTask.id))
            .group_by(ExecutionTask.status)
            .all()
        ),
        approval_decision_counts=_breakdown(
            db.query(ApprovalDecision.decision, func.count(ApprovalDecision.id))
            .group_by(ApprovalDecision.decision)
            .all()
        ),
        execution_mode_counts=_breakdown(
            db.query(Node.execution_mode, func.count(Node.id))
            .group_by(Node.execution_mode)
            .all()
        ),
        environment_counts=_breakdown(
            db.query(Node.environment, func.count(Node.id))
            .group_by(Node.environment)
            .all()
        ),
        failure_type_counts=_breakdown(
            db.query(Incident.failure_type, func.count(Incident.id))
            .group_by(Incident.failure_type)
            .order_by(func.count(Incident.id).desc())
            .limit(5)
            .all()
        ),
        successful_remediations_over_time=[
            TimeSeriesPoint(date=date_key, value=value)
            for date_key, value in remediation_counts_by_day.items()
        ],
    )
