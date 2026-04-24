from __future__ import annotations

import asyncio
import json
import logging
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine, migrate_sqlite_schema
from app.models import ApprovalDecision, Credential, ExecutionTask, HealthCheckResult, Incident, Node, RemediationProfile, User, utcnow
from app.services.ai_service import AIRecommendationService
from app.services.incident_workflow import run_and_record_health_check, write_audit_log

logger = logging.getLogger(__name__)
settings = get_settings()
ai_service = AIRecommendationService()
SUCCESSFUL_EXIT_CODES = {0, 3}


@dataclass(frozen=True)
class ParsedTarget:
    transport: str
    location: str | None
    subject: str


def parse_target(raw_target: str) -> ParsedTarget:
    parts = raw_target.split(":", 2)
    if len(parts) == 1:
        return ParsedTarget(transport="local", location=None, subject=raw_target)
    if parts[0] == "local" and len(parts) == 2:
        return ParsedTarget(transport="local", location=None, subject=parts[1])
    if parts[0] in {"ssh", "api"} and len(parts) == 3:
        return ParsedTarget(transport=parts[0], location=parts[1], subject=parts[2])
    return ParsedTarget(transport="local", location=None, subject=raw_target)


def _default_profile(db: Session) -> RemediationProfile:
    profile = db.query(RemediationProfile).filter(RemediationProfile.name == "command-executor").first()
    if profile:
        return profile
    profile = db.query(RemediationProfile).order_by(RemediationProfile.id.asc()).first()
    if profile:
        return profile
    profile = RemediationProfile(
        name="command-executor",
        description="Compatibility profile for approved command execution.",
        allowed_action_keys=["approved_command"],
        allowed_targets=["*"],
        approval_required=True,
        cooldown_seconds=0,
        retry_limit=1,
        post_action_validation={"mode": "rerun_health_check"},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _proposal_for_incident(incident: Incident, proposal_id: str) -> dict:
    if not incident.recommendations:
        raise ValueError("No recommendation available for this incident")
    recommendation = max(incident.recommendations, key=lambda item: (item.created_at, item.id))
    for proposal in recommendation.proposed_actions:
        if proposal.get("proposal_id") == proposal_id:
            return proposal
    raise ValueError("Command proposal not found")


def _is_successful_exit(exit_code: int) -> bool:
    return exit_code in SUCCESSFUL_EXIT_CODES


def _build_follow_up_context(db: Session, node: Node, incident: Incident) -> tuple[list[dict], list[dict]]:
    recent_checks = [
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
            .filter(HealthCheckResult.node_id == node.id)
            .order_by(desc(HealthCheckResult.checked_at))
            .limit(10)
            .all()
        )
    ]
    recent_executions = (
        db.query(ExecutionTask)
        .filter(ExecutionTask.incident_id == incident.id)
        .order_by(desc(ExecutionTask.queued_at), desc(ExecutionTask.id))
        .limit(8)
        .all()
    )
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
    return recent_checks + ai_service.latest_execution_context(node, recent_executions), prior_incidents


def _create_follow_up_recommendation(db: Session, node: Node, incident: Incident, task: ExecutionTask, health_status: str) -> None:
    if not incident.is_active or incident.archived_at is not None or health_status == "healthy":
        return

    recent_history, prior_incidents = _build_follow_up_context(db, node, incident)
    recent_history.append(
        {
            "kind": "runner_follow_up",
            "details": "An approved command completed and the incident still needs the next remediation or diagnostic step.",
            "execution_task_id": task.id,
            "exit_code": task.exit_code,
            "post_validation_status": task.post_validation_status,
        }
    )
    payload = ai_service.generate(
        node=node,
        incident=incident,
        recent_history=recent_history,
        prior_incidents=prior_incidents,
        workflow_mode="root_cause" if incident.status == "investigating" else "remediation",
    )
    recommendation = ai_service.persist(incident=incident, node=node, payload=payload)
    db.add(recommendation)
    write_audit_log(
        db,
        actor=None,
        entity_type="incident",
        entity_id=str(incident.id),
        action="ai_follow_up_generated",
        details={"execution_task_id": task.id, "post_validation_status": health_status},
    )


def queue_execution(
    db: Session,
    *,
    incident: Incident,
    proposal_id: str,
    approver: User,
    note: str | None = None,
    recommendation_id: int | None = None,
) -> ExecutionTask:
    node = db.query(Node).filter(Node.id == incident.node_id).first()
    if not node:
        raise ValueError("Node not found")

    proposal = _proposal_for_incident(incident, proposal_id)
    profile = _default_profile(db)
    task = ExecutionTask(
        incident_id=incident.id,
        node_id=node.id,
        profile_id=profile.id,
        action_key="approved_command",
        proposal_id=proposal["proposal_id"],
        proposal_title=proposal["title"],
        target=node.execution_target,
        parameters={"risk_level": proposal.get("risk_level", "medium")},
        execution_method=node.execution_mode,
        execution_mode=node.execution_mode,
        approved_command=proposal["command"],
        command_preview=proposal["command"],
        status="queued",
        requested_by_id=approver.id,
        approved_by_id=approver.id,
    )
    db.add(task)
    db.flush()
    db.add(
        ApprovalDecision(
            incident_id=incident.id,
            recommendation_id=recommendation_id,
            execution_task_id=task.id,
            action_key=proposal["proposal_id"],
            decision="approved",
            note=note,
            decided_by_id=approver.id,
        )
    )
    write_audit_log(
        db,
        actor=approver,
        entity_type="execution_task",
        entity_id=str(task.id),
        action="queued",
        details={
            "incident_id": incident.id,
            "proposal_id": proposal["proposal_id"],
            "execution_mode": node.execution_mode,
            "command": proposal["command"],
        },
    )
    db.commit()
    db.refresh(task)
    return task


def reject_execution(
    db: Session,
    *,
    incident: Incident,
    proposal_id: str,
    actor: User,
    note: str | None = None,
    recommendation_id: int | None = None,
) -> None:
    db.add(
        ApprovalDecision(
            incident_id=incident.id,
            recommendation_id=recommendation_id,
            action_key=proposal_id,
            decision="rejected",
            note=note,
            decided_by_id=actor.id,
        )
    )
    write_audit_log(
        db,
        actor=actor,
        entity_type="incident",
        entity_id=str(incident.id),
        action="remediation_rejected",
        details={"proposal_id": proposal_id, "note": note},
    )
    db.commit()


class RunnerDaemon:
    def __init__(self) -> None:
        self._running = False
        Base.metadata.create_all(bind=engine)
        migrate_sqlite_schema()

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:
                logger.exception("Runner daemon error: %s", exc)
            await asyncio.sleep(settings.runner_poll_seconds)

    def stop(self) -> None:
        self._running = False

    def run_once(self) -> None:
        db = SessionLocal()
        try:
            tasks = (
                db.query(ExecutionTask)
                .filter(ExecutionTask.status == "queued")
                .order_by(ExecutionTask.queued_at.asc())
                .all()
            )
            for task in tasks:
                self._execute_task(db, task)
        finally:
            db.close()

    def _execute_task(self, db: Session, task: ExecutionTask) -> None:
        node = db.query(Node).filter(Node.id == task.node_id).first()
        incident = db.query(Incident).filter(Incident.id == task.incident_id).first()
        if not node or not incident or not task.approved_command:
            task.status = "failed"
            task.output = "Execution task is missing node, incident, or approved command."
            task.finished_at = utcnow()
            db.commit()
            return

        credential = db.query(Credential).filter(Credential.id == node.credential_id).first() if node.credential_id else None
        task.status = "running"
        task.started_at = utcnow()
        db.commit()

        exit_code, output = self._dispatch(node, task.approved_command, credential)
        task.exit_code = exit_code
        task.output = output[:8000]
        task.finished_at = utcnow()
        task.status = "success" if _is_successful_exit(exit_code) else "failed"
        db.commit()

        health_row = run_and_record_health_check(db, node)
        task.post_validation_status = health_row.status
        _create_follow_up_recommendation(db, node, incident, task, health_row.status)
        db.commit()

    def _dispatch(self, node: Node, command: str, credential: Credential | None) -> tuple[int, str]:
        if node.execution_mode == "agent":
            return self._run_agent(node.execution_target, command, credential)

        parsed = parse_target(node.execution_target)
        if parsed.transport == "ssh" and parsed.location:
            return self._run_ssh(parsed.location, command, credential)
        if parsed.transport == "api" and parsed.location:
            return self._run_api(parsed.location, parsed.subject, command, credential)
        return self._run_subprocess(shlex.split(command))

    def _run_subprocess(self, command: list[str]) -> tuple[int, str]:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
            output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
            return completed.returncode, output
        except subprocess.TimeoutExpired:
            return 124, "Execution timed out after 60 seconds."
        except FileNotFoundError as exc:
            return 127, str(exc)

    def _run_ssh(self, location: str, command: str, credential: Credential | None) -> tuple[int, str]:
        if not credential or credential.kind not in {"ssh_key", "ssh_password"}:
            return 1, "SSH execution requires an ssh_key or ssh_password credential."

        username = credential.username or "root"
        if credential.kind == "ssh_password":
            return self._run_subprocess(
                [
                    "sshpass",
                    "-p",
                    credential.secret_value,
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "PreferredAuthentications=password",
                    "-o",
                    "PubkeyAuthentication=no",
                    f"{username}@{location}",
                    command,
                ]
            )

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
            handle.write(credential.secret_value)
            key_path = Path(handle.name)
        key_path.chmod(0o600)
        try:
            return self._run_subprocess(
                [
                    "ssh",
                    "-i",
                    str(key_path),
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "PreferredAuthentications=publickey",
                    "-o",
                    "PasswordAuthentication=no",
                    f"{username}@{location}",
                    command,
                ]
            )
        finally:
            key_path.unlink(missing_ok=True)

    def _run_api(self, endpoint: str, subject: str, command: str, credential: Credential | None) -> tuple[int, str]:
        headers = self._credential_headers(credential)
        try:
            response = httpx.post(
                endpoint.rstrip("/") + "/execute",
                json={"target": subject, "command": command},
                headers=headers,
                timeout=30.0,
            )
            return (0 if response.is_success else response.status_code, response.text)
        except Exception as exc:
            return 1, json.dumps({"error": str(exc)})

    def _run_agent(self, endpoint: str, command: str, credential: Credential | None) -> tuple[int, str]:
        headers = self._credential_headers(credential)
        try:
            response = httpx.post(
                endpoint.rstrip("/") + "/execute",
                json={"command": command},
                headers=headers,
                timeout=30.0,
            )
            if response.is_success:
                payload = response.json()
                return int(payload.get("exit_code", 0)), payload.get("output", "")
            return response.status_code, response.text
        except Exception as exc:
            return 1, json.dumps({"error": str(exc)})

    def _credential_headers(self, credential: Credential | None) -> dict[str, str]:
        if not credential:
            return {}
        if credential.kind in {"bearer_token", "agent_token"}:
            return {"Authorization": f"Bearer {credential.secret_value}"}
        return {}


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    daemon = RunnerDaemon()
    await daemon.run()


if __name__ == "__main__":
    asyncio.run(main())
