from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import AIRecommendation, AlertMessage, AuditLog, HealthCheckResult, Incident, Node, User, utcnow
from app.services.ai_service import AIRecommendationService
from app.services.health_checks import run_health_check

ai_service = AIRecommendationService()


def write_audit_log(db: Session, *, actor: User | None, entity_type: str, entity_id: str, action: str, details: dict) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details_json=details,
        )
    )


def _consecutive_failure_count(db: Session, node: Node, lookback: int = 20) -> int:
    recent = (
        db.query(HealthCheckResult)
        .filter(HealthCheckResult.node_id == node.id)
        .order_by(desc(HealthCheckResult.checked_at))
        .limit(lookback)
        .all()
    )
    failures = 0
    for item in recent:
        if item.success:
            break
        failures += 1
    return failures


def _create_recommendation(db: Session, node: Node, incident: Incident) -> AIRecommendation:
    recent_history = [
        {
            "status": check.status,
            "success": check.success,
            "http_status": check.http_status,
            "error_type": check.error_type,
            "checked_at": check.checked_at.isoformat(),
        }
        for check in (
            db.query(HealthCheckResult)
            .filter(HealthCheckResult.node_id == node.id)
            .order_by(desc(HealthCheckResult.checked_at))
            .limit(10)
            .all()
        )
    ]
    prior_incidents = [
        {
            "failure_type": item.failure_type,
            "summary": item.summary,
            "started_at": item.started_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }
        for item in (
            db.query(Incident)
            .filter(Incident.node_id == node.id, Incident.id != incident.id)
            .order_by(desc(Incident.started_at))
            .limit(5)
            .all()
        )
    ]
    payload = ai_service.generate(node=node, incident=incident, recent_history=recent_history, prior_incidents=prior_incidents)
    recommendation = ai_service.persist(incident=incident, node=node, payload=payload)
    db.add(recommendation)
    return recommendation


def _create_alert_message(db: Session, incident: Incident, node: Node) -> None:
    db.add(
        AlertMessage(
            incident_id=incident.id,
            channel_type="internal",
            status="open",
            title=f"{node.name} outage detected",
            body=incident.summary,
            payload={"node_id": node.id, "incident_id": incident.id},
        )
    )


def _resolve_active_incident(db: Session, node: Node) -> None:
    incident = (
        db.query(Incident)
        .filter(Incident.node_id == node.id, Incident.is_active.is_(True))
        .order_by(desc(Incident.started_at))
        .first()
    )
    if not incident:
        return

    incident.status = "resolved"
    incident.is_active = False
    incident.resolved_at = utcnow()


def process_health_result(db: Session, node: Node, result: dict, actor: User | None = None) -> HealthCheckResult:
    health_row = HealthCheckResult(
        node_id=node.id,
        status=result["status"],
        success=result["success"],
        latency_ms=result.get("latency_ms"),
        http_status=result.get("http_status"),
        error_type=result.get("error_type"),
        error_detail=result.get("error_detail"),
        response_excerpt=result.get("response_excerpt"),
    )
    db.add(health_row)

    node.last_check_at = utcnow()
    if result["success"]:
        node.current_status = "healthy"
        _resolve_active_incident(db, node)
        write_audit_log(
            db,
            actor=actor,
            entity_type="node",
            entity_id=str(node.id),
            action="health_check_passed",
            details={"status": "healthy"},
        )
        return health_row

    recent_failures = _consecutive_failure_count(db, node) + 1
    node.current_status = "down" if recent_failures >= node.retry_count else "degraded"

    active_incident = (
        db.query(Incident)
        .filter(Incident.node_id == node.id, Incident.is_active.is_(True))
        .order_by(desc(Incident.started_at))
        .first()
    )
    if active_incident:
        active_incident.last_failure_at = utcnow()
        active_incident.details_json = {
            **active_incident.details_json,
            "latest_error_type": result.get("error_type"),
            "latest_error_detail": result.get("error_detail"),
        }
    elif recent_failures >= node.retry_count:
        summary = f"{node.name} failed {node.retry_count} consecutive checks: {result.get('error_type', 'unknown failure')}"
        incident = Incident(
            node_id=node.id,
            status="open",
            severity="high",
            failure_type=result.get("error_type") or "unknown_failure",
            summary=summary,
            details_json={
                "error_type": result.get("error_type"),
                "error_detail": result.get("error_detail"),
                "http_status": result.get("http_status"),
                "response_excerpt": result.get("response_excerpt"),
            },
        )
        node.last_incident_at = utcnow()
        db.add(incident)
        db.flush()
        _create_alert_message(db, incident, node)
        _create_recommendation(db, node, incident)
        write_audit_log(
            db,
            actor=actor,
            entity_type="incident",
            entity_id=str(incident.id),
            action="incident_created",
            details={"node_id": node.id, "failure_type": incident.failure_type},
        )

    write_audit_log(
        db,
        actor=actor,
        entity_type="node",
        entity_id=str(node.id),
        action="health_check_failed",
        details=result,
    )
    return health_row


def run_and_record_health_check(db: Session, node: Node, actor: User | None = None) -> HealthCheckResult:
    result = run_health_check(node)
    health_row = process_health_result(db, node, result, actor=actor)
    db.commit()
    db.refresh(node)
    return health_row
