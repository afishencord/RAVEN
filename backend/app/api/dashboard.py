from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import ApprovalDecision, ExecutionTask, Incident, Node, User, utcnow
from app.schemas import DashboardMetricsRead, MetricBreakdownItem, TimeSeriesPoint

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DashboardRange = str


def _range_start(range_key: DashboardRange):
    now = utcnow()
    if range_key == "7d":
        return now - timedelta(days=7)
    if range_key == "30d":
        return now - timedelta(days=30)
    if range_key == "365d":
        return now - timedelta(days=365)
    return now - timedelta(hours=24)


def _remediation_buckets(range_key: DashboardRange):
    now = utcnow()
    if range_key == "24h":
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        buckets = [
            (current_hour - timedelta(hours=23 - offset)).isoformat()
            for offset in range(24)
        ]
        return buckets, lambda value: value.replace(minute=0, second=0, microsecond=0).isoformat()

    if range_key == "365d":
        day_count = 365
    else:
        day_count = 30 if range_key == "30d" else 7
    window_start = now.date() - timedelta(days=day_count - 1)
    buckets = [(window_start + timedelta(days=offset)).isoformat() for offset in range(day_count)]
    return buckets, lambda value: value.date().isoformat()


def _breakdown(rows: list[tuple[str | None, int]], fallback_label: str = "Unknown") -> list[MetricBreakdownItem]:
    return [
        MetricBreakdownItem(label=label or fallback_label, value=value)
        for label, value in rows
    ]


@router.get("/metrics", response_model=DashboardMetricsRead)
def get_dashboard_metrics(
    range_key: DashboardRange = Query(default="24h", alias="range", pattern="^(24h|7d|30d|365d)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    window_start = _range_start(range_key)
    bucket_keys, bucket_key_for = _remediation_buckets(range_key)

    total_nodes = db.query(func.count(Node.id)).scalar() or 0
    enabled_nodes = db.query(func.count(Node.id)).filter(Node.is_enabled.is_(True)).scalar() or 0
    active_incidents = (
        db.query(func.count(Incident.id))
        .filter(
            Incident.is_active.is_(True),
            Incident.archived_at.is_(None),
            Incident.last_failure_at >= window_start,
        )
        .scalar()
        or 0
    )
    resolved_incidents = (
        db.query(func.count(Incident.id))
        .filter(Incident.resolved_at.isnot(None), Incident.resolved_at >= window_start)
        .scalar()
        or 0
    )
    successful_remediations = (
        db.query(func.count(ExecutionTask.id))
        .filter(
            ExecutionTask.status == "success",
            ExecutionTask.post_validation_status == "healthy",
            ExecutionTask.finished_at.isnot(None),
            ExecutionTask.finished_at >= window_start,
        )
        .scalar()
        or 0
    )

    resolved_rows = (
        db.query(Incident.started_at, Incident.resolved_at)
        .filter(Incident.resolved_at.isnot(None), Incident.resolved_at >= window_start)
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
            ExecutionTask.finished_at >= window_start,
        )
        .all()
    )
    remediation_counts_by_day: dict[str, int] = {
        bucket_key: 0
        for bucket_key in bucket_keys
    }
    for (finished_at,) in successful_executions:
        date_key = bucket_key_for(finished_at)
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
            .filter(ExecutionTask.queued_at >= window_start)
            .group_by(ExecutionTask.status)
            .all()
        ),
        approval_decision_counts=_breakdown(
            db.query(ApprovalDecision.decision, func.count(ApprovalDecision.id))
            .filter(ApprovalDecision.decided_at >= window_start)
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
            .filter(or_(Incident.started_at >= window_start, Incident.last_failure_at >= window_start))
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
