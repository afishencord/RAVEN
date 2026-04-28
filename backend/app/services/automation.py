from __future__ import annotations

import json
import platform
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import (
    ApprovalDecision,
    AuditLog,
    Credential,
    ExecutionTask,
    Incident,
    Node,
    NodeAutomationEdge,
    NodeRemediationAssignment,
    NodeValidationAssignment,
    RemediationDefinition,
    RemediationProfile,
    User,
    ValidationDefinition,
    ValidationRun,
    utcnow,
)
from app.services.ai_service import AIRecommendationService

ai_service = AIRecommendationService()
SUCCESSFUL_EXIT_CODES = {0, 3}


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
        allowed_action_keys=["approved_command", "automated_remediation"],
        allowed_targets=["*"],
        approval_required=True,
        cooldown_seconds=0,
        retry_limit=1,
        post_action_validation={"mode": "rerun_health_check"},
    )
    db.add(profile)
    db.flush()
    return profile


def _system_user(db: Session) -> User | None:
    return db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first() or db.query(User).order_by(User.id.asc()).first()


def _credential_headers(credential: Credential | None) -> dict[str, str]:
    if not credential:
        return {}
    if credential.kind in {"bearer_token", "agent_token"}:
        return {"Authorization": f"Bearer {credential.secret_value}"}
    return {}


def _run_subprocess(command: list[str], timeout: int) -> tuple[int, str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
        return completed.returncode, output
    except subprocess.TimeoutExpired:
        return 124, f"Execution timed out after {timeout} seconds."
    except FileNotFoundError as exc:
        return 127, str(exc)


def _run_ssh(location: str, command: str, credential: Credential | None, timeout: int) -> tuple[int, str]:
    if not credential or credential.kind not in {"ssh_key", "ssh_password"}:
        return 1, "SSH validation requires an ssh_key or ssh_password credential."

    username = credential.username or "root"
    if credential.kind == "ssh_password":
        return _run_subprocess(
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
            ],
            timeout,
        )

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
        handle.write(credential.secret_value)
        key_path = Path(handle.name)
    key_path.chmod(0o600)
    try:
        return _run_subprocess(
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
            ],
            timeout,
        )
    finally:
        key_path.unlink(missing_ok=True)


def _run_api(endpoint: str, subject: str, command: str, credential: Credential | None, timeout: int) -> tuple[int, str]:
    try:
        response = httpx.post(
            endpoint.rstrip("/") + "/execute",
            json={"target": subject, "command": command},
            headers=_credential_headers(credential),
            timeout=float(timeout),
        )
        return (0 if response.is_success else response.status_code, response.text)
    except Exception as exc:
        return 1, json.dumps({"error": str(exc)})


def _run_agent(endpoint: str, command: str, credential: Credential | None, timeout: int) -> tuple[int, str]:
    try:
        response = httpx.post(
            endpoint.rstrip("/") + "/execute",
            json={"command": command},
            headers=_credential_headers(credential),
            timeout=float(timeout),
        )
        if response.is_success:
            payload = response.json()
            return int(payload.get("exit_code", 0)), payload.get("output", "")
        return response.status_code, response.text
    except Exception as exc:
        return 1, json.dumps({"error": str(exc)})


def _dispatch_validation_command(db: Session, node: Node, command: str, timeout: int) -> tuple[int, str]:
    credential = db.query(Credential).filter(Credential.id == node.credential_id).first() if node.credential_id else None
    if node.execution_mode == "agent":
        return _run_agent(node.execution_target, command, credential, timeout)

    parsed = parse_target(node.execution_target)
    if parsed.transport == "ssh" and parsed.location:
        return _run_ssh(parsed.location, command, credential, timeout)
    if parsed.transport == "api" and parsed.location:
        return _run_api(parsed.location, parsed.subject, command, credential, timeout)
    return _run_subprocess(shlex.split(command), timeout)


def _validation_url(node: Node, validation: ValidationDefinition) -> str:
    if validation.url:
        base = validation.url
    elif node.url:
        base = node.url
    else:
        scheme = "https" if node.health_check_type == "https" else "http"
        port = f":{node.port}" if node.port else ""
        base = f"{scheme}://{node.host}{port}"
    path = validation.path if validation.path is not None else node.health_check_path
    if path:
        return urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    return base


def run_validation_definition(db: Session, *, node: Node, validation: ValidationDefinition, incident: Incident | None = None) -> ValidationRun:
    started = utcnow()
    run = ValidationRun(
        node_id=node.id,
        incident_id=incident.id if incident else None,
        validation_id=validation.id,
        status="running",
        started_at=started,
    )
    db.add(run)
    db.flush()

    try:
        if validation.validation_type == "command":
            if not validation.command:
                raise ValueError("Command validation requires a command.")
            exit_code, output = _dispatch_validation_command(db, node, validation.command, max(validation.timeout_seconds, 1))
            matched = exit_code == validation.expected_exit_code
            evaluation: dict | None = None
            if validation.expected_response_contains:
                evaluation = ai_service.evaluate_validation_output(
                    validation_name=validation.name,
                    expected_condition=validation.expected_response_contains,
                    observed_output=output,
                    observed_exit_code=exit_code,
                )
                matched = bool(evaluation["matched"])
            run.observed_exit_code = exit_code
            if evaluation:
                run.output = (
                    f"{output[:6000]}\n\n"
                    f"LLM validation match: {evaluation['matched']}\n"
                    f"Summary: {evaluation['summary']}\n"
                    f"Rationale: {evaluation['rationale']}"
                )[:8000]
            else:
                run.output = output[:8000]
            run.matched_expectation = matched
            run.status = "passed" if matched else "failed"
        else:
            url = _validation_url(node, validation)
            start = time.perf_counter()
            response = httpx.get(url, timeout=max(validation.timeout_seconds, 1), follow_redirects=True)
            latency_ms = int((time.perf_counter() - start) * 1000)
            excerpt = response.text[:8000]
            expected_status = validation.expected_status_code or 200
            matched = response.status_code == expected_status
            evaluation = None
            if validation.expected_response_contains:
                evaluation = ai_service.evaluate_validation_output(
                    validation_name=validation.name,
                    expected_condition=validation.expected_response_contains,
                    observed_output=response.text,
                    observed_status_code=response.status_code,
                )
                matched = bool(evaluation["matched"])
            run.observed_status_code = response.status_code
            if evaluation:
                run.output = (
                    f"GET {url}\nLatency: {latency_ms} ms\n\n{excerpt[:5500]}\n\n"
                    f"LLM validation match: {evaluation['matched']}\n"
                    f"Summary: {evaluation['summary']}\n"
                    f"Rationale: {evaluation['rationale']}"
                )[:8000]
            else:
                run.output = f"GET {url}\nLatency: {latency_ms} ms\n\n{excerpt}"[:8000]
            run.matched_expectation = matched
            run.status = "passed" if matched else "failed"
    except Exception as exc:
        run.status = "error"
        run.matched_expectation = False
        run.error_detail = str(exc)[:2000]
    finally:
        run.finished_at = utcnow()
        db.flush()

    return run


def _validation_context(run: ValidationRun) -> dict:
    return {
        "validation_run_id": run.id,
        "validation_id": run.validation_id,
        "validation_name": run.validation.name if run.validation else None,
        "status": run.status,
        "matched_expectation": run.matched_expectation,
        "observed_status_code": run.observed_status_code,
        "observed_exit_code": run.observed_exit_code,
        "output_excerpt": (run.output or run.error_detail or "")[:1500],
    }


def _remediation_context(assignment: NodeRemediationAssignment) -> dict:
    remediation = assignment.remediation
    return {
        "id": remediation.id,
        "name": remediation.name,
        "description": remediation.description,
        "command": remediation.command,
        "risk_level": remediation.risk_level,
        "execution_mode": assignment.node.execution_mode if assignment.node else remediation.execution_mode,
    }


def _eligible_remediations(
    db: Session,
    *,
    node: Node,
    validations: list[NodeValidationAssignment],
    remediations: list[NodeRemediationAssignment],
    validation_runs: list[ValidationRun],
) -> tuple[list[NodeRemediationAssignment], list[dict], str]:
    run_by_validation_id = {run.validation_id: run for run in validation_runs}
    validation_ids = {assignment.validation_id for assignment in validations}
    remediation_ids = {assignment.remediation_id for assignment in remediations}
    edges = (
        db.query(NodeAutomationEdge)
        .filter(
            NodeAutomationEdge.node_id == node.id,
            NodeAutomationEdge.is_enabled.is_(True),
            NodeAutomationEdge.validation_id.in_(validation_ids),
            NodeAutomationEdge.remediation_id.in_(remediation_ids),
        )
        .order_by(NodeAutomationEdge.sort_order.asc(), NodeAutomationEdge.id.asc())
        .all()
    )

    if not edges:
        all_matched = all(run.matched_expectation for run in validation_runs)
        return (
            remediations if all_matched else [],
            [
                {
                    "mode": "implicit_all_validations",
                    "remediation_id": assignment.remediation_id,
                    "required_validation_ids": [run.validation_id for run in validation_runs],
                    "matched_validation_ids": [run.validation_id for run in validation_runs if run.matched_expectation],
                    "eligible": all_matched,
                }
                for assignment in remediations
            ],
            "implicit_all_validations",
        )

    eligible: list[NodeRemediationAssignment] = []
    details: list[dict] = []
    for assignment in remediations:
        connected = [edge for edge in edges if edge.remediation_id == assignment.remediation_id]
        required_validation_ids = list(dict.fromkeys(edge.validation_id for edge in connected))
        matched_validation_ids = [
            validation_id
            for validation_id in required_validation_ids
            if run_by_validation_id.get(validation_id) and run_by_validation_id[validation_id].matched_expectation
        ]
        is_eligible = bool(required_validation_ids) and len(matched_validation_ids) == len(required_validation_ids)
        if is_eligible:
            eligible.append(assignment)
        details.append(
            {
                "mode": "explicit_playbook_edges",
                "remediation_id": assignment.remediation_id,
                "required_validation_ids": required_validation_ids,
                "matched_validation_ids": matched_validation_ids,
                "eligible": is_eligible,
            }
        )
    return eligible, details, "explicit_playbook_edges"


def queue_automated_remediation(
    db: Session,
    *,
    node: Node,
    incident: Incident,
    remediation: RemediationDefinition,
    validation_runs: list[ValidationRun],
    gate: dict,
    eligibility_details: list[dict],
) -> ExecutionTask | None:
    actor = _system_user(db)
    if not actor:
        write_audit_log(db, actor=None, entity_type="incident", entity_id=str(incident.id), action="automation_skipped", details={"reason": "no_system_user"})
        return None

    profile = _default_profile(db)
    execution_mode = node.execution_mode
    proposal_id = f"auto-remediation-{remediation.id}"
    task = ExecutionTask(
        incident_id=incident.id,
        node_id=node.id,
        profile_id=profile.id,
        action_key="automated_remediation",
        proposal_id=proposal_id,
        proposal_title=remediation.name,
        target=node.execution_target,
        parameters={
            "automation_source": "validation_gate",
            "remediation_definition_id": remediation.id,
            "validation_run_ids": [run.id for run in validation_runs],
            "llm_gate_summary": gate.get("summary"),
            "llm_gate_rationale": gate.get("rationale"),
            "automation_eligibility": eligibility_details,
        },
        execution_method=execution_mode,
        execution_mode=execution_mode,
        approved_command=remediation.command,
        command_preview=remediation.command,
        status="queued",
        requested_by_id=actor.id,
        approved_by_id=actor.id,
    )
    db.add(task)
    db.flush()
    db.add(
        ApprovalDecision(
            incident_id=incident.id,
            execution_task_id=task.id,
            action_key=proposal_id,
            decision="auto_approved",
            note=str(gate.get("rationale") or ""),
            decided_by_id=actor.id,
        )
    )
    write_audit_log(
        db,
        actor=actor,
        entity_type="execution_task",
        entity_id=str(task.id),
        action="queued_auto",
        details={
            "incident_id": incident.id,
            "node_id": node.id,
            "remediation_definition_id": remediation.id,
            "validation_run_ids": [run.id for run in validation_runs],
            "gate": gate,
            "eligibility": eligibility_details,
        },
    )
    return task


def run_incident_automation(db: Session, *, node: Node, incident: Incident) -> None:
    validations = (
        db.query(NodeValidationAssignment)
        .join(ValidationDefinition, ValidationDefinition.id == NodeValidationAssignment.validation_id)
        .filter(
            NodeValidationAssignment.node_id == node.id,
            NodeValidationAssignment.is_enabled.is_(True),
            ValidationDefinition.is_enabled.is_(True),
        )
        .order_by(NodeValidationAssignment.sort_order.asc(), NodeValidationAssignment.id.asc())
        .all()
    )
    remediations = (
        db.query(NodeRemediationAssignment)
        .join(RemediationDefinition, RemediationDefinition.id == NodeRemediationAssignment.remediation_id)
        .filter(
            NodeRemediationAssignment.node_id == node.id,
            NodeRemediationAssignment.is_enabled.is_(True),
            RemediationDefinition.is_enabled.is_(True),
        )
        .order_by(NodeRemediationAssignment.sort_order.asc(), NodeRemediationAssignment.id.asc())
        .all()
    )

    if not validations or not remediations:
        write_audit_log(
            db,
            actor=None,
            entity_type="incident",
            entity_id=str(incident.id),
            action="automation_skipped",
            details={"reason": "missing_assignments", "validations": len(validations), "remediations": len(remediations)},
        )
        return

    validation_runs = [run_validation_definition(db, node=node, validation=assignment.validation, incident=incident) for assignment in validations]
    eligible_remediations, eligibility_details, playbook_mode = _eligible_remediations(
        db,
        node=node,
        validations=validations,
        remediations=remediations,
        validation_runs=validation_runs,
    )
    if not any(run.matched_expectation for run in validation_runs):
        write_audit_log(
            db,
            actor=None,
            entity_type="incident",
            entity_id=str(incident.id),
            action="automation_validation_failed",
            details={"validation_run_ids": [run.id for run in validation_runs], "eligibility": eligibility_details},
        )
        return

    if not eligible_remediations:
        write_audit_log(
            db,
            actor=None,
            entity_type="incident",
            entity_id=str(incident.id),
            action="automation_no_eligible_remediation",
            details={
                "validation_run_ids": [run.id for run in validation_runs],
                "playbook_mode": playbook_mode,
                "eligibility": eligibility_details,
            },
        )
        return

    gate = ai_service.generate_automation_gate(
        node=node,
        incident=incident,
        validation_results=[_validation_context(run) for run in validation_runs],
        remediations=[_remediation_context(assignment) for assignment in eligible_remediations],
    )
    selected_id = gate.get("selected_remediation_id")
    selected = next((assignment.remediation for assignment in eligible_remediations if assignment.remediation_id == selected_id), None)
    if not selected and len(eligible_remediations) == 1 and not getattr(ai_service, "client", None):
        selected = eligible_remediations[0].remediation
        gate = {
            "selected_remediation_id": selected.id,
            "decision": "run",
            "summary": "Single eligible remediation selected after playbook validation matched.",
            "rationale": "The model gate is unavailable, but the playbook produced exactly one eligible remediation.",
        }
    if not selected:
        write_audit_log(
            db,
            actor=None,
            entity_type="incident",
            entity_id=str(incident.id),
            action="automation_no_action",
            details={
                "gate": gate,
                "validation_run_ids": [run.id for run in validation_runs],
                "playbook_mode": playbook_mode,
                "eligibility": eligibility_details,
            },
        )
        return

    queue_automated_remediation(
        db,
        node=node,
        incident=incident,
        remediation=selected,
        validation_runs=validation_runs,
        gate=gate,
        eligibility_details=eligibility_details,
    )


def latest_validation_runs(db: Session, validation_id: int) -> ValidationRun | None:
    return (
        db.query(ValidationRun)
        .filter(ValidationRun.validation_id == validation_id)
        .order_by(desc(ValidationRun.started_at), desc(ValidationRun.id))
        .first()
    )


def ping_command_available() -> bool:
    try:
        args = ["ping", "-c", "1", "127.0.0.1"]
        if platform.system().lower().startswith("darwin"):
            args = ["ping", "-c", "1", "127.0.0.1"]
        subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
        return True
    except Exception:
        return False
