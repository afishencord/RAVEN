from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import AIRecommendation, AlertMessage, AuditLog, ExecutionTask, HealthCheckResult, Incident, Node, NodeHealthCheck, User, utcnow
from app.services.ai_service import AIRecommendationService
from app.services.automation import run_incident_automation
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


def legacy_health_check_payload(node: Node) -> dict:
    config = {}
    if node.url:
        config["url"] = node.url
    if node.health_check_path:
        config["path"] = node.health_check_path
    if node.expected_status_code:
        config["expected_status_code"] = node.expected_status_code
    if node.expected_response_contains:
        config["expected_response_contains"] = node.expected_response_contains
    return config


def ensure_default_health_checks(db: Session, node: Node) -> list[NodeHealthCheck]:
    checks = (
        db.query(NodeHealthCheck)
        .filter(NodeHealthCheck.node_id == node.id)
        .order_by(NodeHealthCheck.sort_order.asc(), NodeHealthCheck.id.asc())
        .all()
    )
    if checks:
        return checks
    check = NodeHealthCheck(
        node_id=node.id,
        name=f"{node.health_check_type.upper()} health",
        check_type=node.health_check_type or "http",
        config_json=legacy_health_check_payload(node),
        interval_seconds=node.check_interval_seconds,
        timeout_seconds=node.timeout_seconds,
        retry_count=node.retry_count,
        sort_order=0,
    )
    db.add(check)
    db.flush()
    return [check]


def _consecutive_failure_count(db: Session, node: Node, health_check: NodeHealthCheck | None = None, lookback: int = 20) -> int:
    query = db.query(HealthCheckResult).filter(HealthCheckResult.node_id == node.id)
    if health_check:
        query = query.filter(HealthCheckResult.health_check_id == health_check.id)
    recent = (
        query
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
            "check_name": check.check_name,
            "check_type": check.check_type,
            "http_status": check.http_status,
            "error_type": check.error_type,
            "error_detail": check.error_detail,
            "response_excerpt": check.response_excerpt,
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
    recent_executions = (
        db.query(ExecutionTask)
        .filter(ExecutionTask.node_id == node.id)
        .order_by(desc(ExecutionTask.queued_at))
        .limit(5)
        .all()
    )
    payload = ai_service.generate(
        node=node,
        incident=incident,
        recent_history=recent_history + ai_service.latest_execution_context(node, recent_executions),
        prior_incidents=prior_incidents,
    )
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


def aggregate_node_status(db: Session, node: Node) -> str:
    checks = db.query(NodeHealthCheck).filter(NodeHealthCheck.node_id == node.id, NodeHealthCheck.is_enabled.is_(True)).all()
    statuses = [check.current_status for check in checks]
    if not statuses:
        return node.current_status
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


def process_health_result(db: Session, node: Node, result: dict, actor: User | None = None, health_check: NodeHealthCheck | None = None) -> HealthCheckResult:
    health_row = HealthCheckResult(
        node_id=node.id,
        health_check_id=health_check.id if health_check else None,
        check_name=health_check.name if health_check else None,
        check_type=health_check.check_type if health_check else node.health_check_type,
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
    if health_check:
        health_check.last_run_at = node.last_check_at
        health_check.last_latency_ms = result.get("latency_ms")
        health_check.last_http_status = result.get("http_status")
        health_check.last_error_type = result.get("error_type")
        health_check.last_error_detail = result.get("error_detail")
        health_check.last_response_excerpt = result.get("response_excerpt")
        if result["success"]:
            health_check.consecutive_failures = 0
            health_check.current_status = "healthy"
            health_check.last_success_at = node.last_check_at
        else:
            health_check.consecutive_failures = _consecutive_failure_count(db, node, health_check) + 1
            health_check.current_status = "down" if health_check.consecutive_failures >= health_check.retry_count else "degraded"
            health_check.last_failure_at = node.last_check_at

    if result["success"]:
        node.current_status = aggregate_node_status(db, node)
        if node.current_status == "healthy":
            _resolve_active_incident(db, node)
        return health_row

    recent_failures = health_check.consecutive_failures if health_check else _consecutive_failure_count(db, node) + 1
    retry_count = health_check.retry_count if health_check else node.retry_count
    node.current_status = aggregate_node_status(db, node) if health_check else ("down" if recent_failures >= retry_count else "degraded")

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
            "latest_check_id": health_check.id if health_check else None,
            "latest_check_name": health_check.name if health_check else None,
            "latest_check_type": health_check.check_type if health_check else node.health_check_type,
            "latest_error_type": result.get("error_type"),
            "latest_error_detail": result.get("error_detail"),
        }
    elif recent_failures >= retry_count:
        check_label = f" ({health_check.name})" if health_check else ""
        summary = f"{node.name}{check_label} failed {retry_count} consecutive checks: {result.get('error_type', 'unknown failure')}"
        incident = Incident(
            node_id=node.id,
            status="open",
            severity="high",
            failure_type=result.get("error_type") or "unknown_failure",
            summary=summary,
            details_json={
                "check_id": health_check.id if health_check else None,
                "check_name": health_check.name if health_check else None,
                "check_type": health_check.check_type if health_check else node.health_check_type,
                "check_config": health_check.config_json if health_check else legacy_health_check_payload(node),
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
        run_incident_automation(db, node=node, incident=incident)
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
    rows: list[HealthCheckResult] = []
    checks = [check for check in ensure_default_health_checks(db, node) if check.is_enabled]
    for check in checks:
        result = run_health_check(node, check, db=db)
        rows.append(process_health_result(db, node, result, actor=actor, health_check=check))
    if not rows:
        result = run_health_check(node, db=db)
        rows.append(process_health_result(db, node, result, actor=actor))
    node.current_status = aggregate_node_status(db, node)
    db.commit()
    db.refresh(node)
    return next((row for row in rows if not row.success), rows[-1])
