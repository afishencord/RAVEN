from __future__ import annotations

import asyncio
import json
import logging
import shlex
import subprocess
from dataclasses import dataclass

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import ApprovalDecision, ExecutionTask, Incident, Node, RemediationProfile, User, utcnow
from app.services.health_checks import build_health_url
from app.services.incident_workflow import run_and_record_health_check, write_audit_log
from app.services.remediation_catalog import get_action, render_command

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class ParsedTarget:
    transport: str
    location: str | None
    subject: str


def parse_target(raw_target: str) -> ParsedTarget:
    parts = raw_target.split(":", 2)
    if len(parts) == 1:
        return ParsedTarget(transport="local", location=None, subject=raw_target)
    if parts[0] in {"local", "script"} and len(parts) == 2:
        return ParsedTarget(transport=parts[0], location=None, subject=parts[1])
    if parts[0] in {"ssh", "api"} and len(parts) == 3:
        return ParsedTarget(transport=parts[0], location=parts[1], subject=parts[2])
    return ParsedTarget(transport="local", location=None, subject=raw_target)


def _load_profile(db: Session, node: Node) -> RemediationProfile:
    profile = db.query(RemediationProfile).filter(RemediationProfile.name == node.remediation_profile).first()
    if not profile:
        raise ValueError(f"Remediation profile {node.remediation_profile} not found")
    return profile


def _validate_queue_request(db: Session, node: Node, profile: RemediationProfile, action_key: str) -> None:
    if action_key not in profile.allowed_action_keys:
        raise ValueError("Action is not allowed by the remediation profile")
    if node.execution_target not in profile.allowed_targets and "*" not in profile.allowed_targets:
        raise ValueError("Execution target is not allowed by the remediation profile")

    last_task = (
        db.query(ExecutionTask)
        .filter(ExecutionTask.node_id == node.id, ExecutionTask.action_key == action_key)
        .order_by(desc(ExecutionTask.queued_at))
        .first()
    )
    if last_task and last_task.finished_at:
        cooldown_elapsed = (utcnow() - last_task.finished_at).total_seconds()
        if cooldown_elapsed < profile.cooldown_seconds:
            raise ValueError("Action is still in cooldown for this node")


def queue_execution(
    db: Session,
    *,
    incident: Incident,
    action_key: str,
    approver: User,
    note: str | None = None,
    recommendation_id: int | None = None,
) -> ExecutionTask:
    node = db.query(Node).filter(Node.id == incident.node_id).first()
    if not node:
        raise ValueError("Node not found")
    profile = _load_profile(db, node)
    _validate_queue_request(db, node, profile, action_key)
    parsed = parse_target(node.execution_target)
    preview = render_command(action_key, target=parsed.subject, url=build_health_url(node))
    action = get_action(action_key)
    execution_method = parsed.transport if parsed.transport in {"ssh", "api"} else action.execution_method.replace("_or_ssh", "")

    task = ExecutionTask(
        incident_id=incident.id,
        node_id=node.id,
        profile_id=profile.id,
        action_key=action_key,
        target=node.execution_target,
        parameters={"target_subject": parsed.subject},
        execution_method=execution_method,
        command_preview=preview,
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
            action_key=action_key,
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
        details={"incident_id": incident.id, "action_key": action_key, "execution_method": execution_method},
    )
    db.commit()
    db.refresh(task)
    return task


def reject_execution(
    db: Session,
    *,
    incident: Incident,
    action_key: str,
    actor: User,
    note: str | None = None,
    recommendation_id: int | None = None,
) -> None:
    db.add(
        ApprovalDecision(
            incident_id=incident.id,
            recommendation_id=recommendation_id,
            action_key=action_key,
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
        details={"action_key": action_key, "note": note},
    )
    db.commit()


class RunnerDaemon:
    def __init__(self) -> None:
        self._running = False

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
        if not node or not incident:
            task.status = "failed"
            task.output = "Node or incident missing for execution task."
            task.finished_at = utcnow()
            db.commit()
            return

        parsed = parse_target(task.target)
        task.status = "running"
        task.started_at = utcnow()
        db.commit()

        exit_code, output = self._dispatch(task.command_preview, parsed, task.action_key)
        task.exit_code = exit_code
        task.output = output[:4000]
        task.finished_at = utcnow()
        task.status = "success" if exit_code == 0 else "failed"
        db.commit()

        health_row = run_and_record_health_check(db, node)
        task.post_validation_status = health_row.status
        db.commit()

    def _dispatch(self, command: str, parsed: ParsedTarget, action_key: str) -> tuple[int, str]:
        if parsed.transport == "ssh" and parsed.location:
            return self._run_subprocess(["ssh", parsed.location, command])
        if parsed.transport == "api" and parsed.location:
            return self._run_api(parsed.location, parsed.subject, action_key)
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

    def _run_api(self, endpoint: str, subject: str, action_key: str) -> tuple[int, str]:
        try:
            response = httpx.post(
                endpoint.rstrip("/") + "/execute",
                json={"action_key": action_key, "target": subject},
                timeout=30.0,
            )
            return (0 if response.is_success else response.status_code, response.text)
        except Exception as exc:
            return 1, json.dumps({"error": str(exc)})


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    daemon = RunnerDaemon()
    await daemon.run()


if __name__ == "__main__":
    asyncio.run(main())
