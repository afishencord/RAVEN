from __future__ import annotations

import json
import re
from hashlib import sha1

from openai import OpenAI

from app.config import get_settings
from app.models import AIRecommendation, ExecutionTask, Incident, Node
from app.services.health_checks import build_health_url

settings = get_settings()


def _extract_json_payload(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw_text)


def _slugify(text: str) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return collapsed or "proposal"


def _target_summary(node: Node) -> str:
    if node.execution_mode == "agent":
        return f"agent:{node.execution_target}"
    return node.execution_target


def _latest_output_excerpt(recent_history: list[dict], limit: int = 700) -> str:
    for item in recent_history:
        output = item.get("output_excerpt")
        if output:
            return str(output).strip()[:limit]
    return ""


def _previous_proposal_ids(incident: Incident) -> set[str]:
    proposal_ids: set[str] = set()
    for recommendation in incident.recommendations or []:
        for proposal in recommendation.proposed_actions or []:
            proposal_id = proposal.get("proposal_id")
            if proposal_id:
                proposal_ids.add(str(proposal_id))
    return proposal_ids


def _unique_proposal_id(base: str, existing: set[str], seed: str) -> str:
    slug = _slugify(base)
    if slug not in existing:
        existing.add(slug)
        return slug
    suffix = sha1(seed.encode("utf-8")).hexdigest()[:8]
    candidate = f"{slug}-{suffix}"
    counter = 2
    while candidate in existing:
        candidate = f"{slug}-{suffix}-{counter}"
        counter += 1
    existing.add(candidate)
    return candidate


def _sentence_limit(text: str, max_sentences: int = 5) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [part.strip() for part in parts if part.strip()]
    if not sentences:
        return text.strip()
    return " ".join(sentences[:max_sentences])


def _fallback_commands(node: Node, incident: Incident, recent_history: list[dict] | None = None, existing_ids: set[str] | None = None) -> list[dict]:
    health_url = build_health_url(node)
    subject = node.context_text or node.execution_target
    recent_history = recent_history or []
    existing_ids = set(existing_ids or set())
    output_excerpt = _latest_output_excerpt(recent_history)
    if output_excerpt:
        follow_up_commands = [
            (
                "validate-current-health",
                f"curl -i {health_url}",
                "Validate whether the service is still returning the expected health response after the last command.",
            ),
            (
                "inspect-runtime-state",
                "docker inspect --format '{{json .State}}' <container_name>",
                "Inspect runtime state because the prior command output should be correlated with container status.",
            ),
            (
                "inspect-recent-logs",
                "docker logs --tail 200 <container_name>",
                "Collect fresh logs after the prior command to see whether the same failure signature is still present.",
            ),
        ]
        commands = []
        for key, command, rationale in follow_up_commands:
            commands.append(
                {
                    "proposal_id": _unique_proposal_id(f"{node.name}-{key}", existing_ids, f"{incident.id}:{key}:{output_excerpt}"),
                    "title": key.replace("-", " ").title(),
                    "command": command,
                    "rationale": f"{rationale} Observed output excerpt: {output_excerpt}",
                    "execution_mode": node.execution_mode,
                    "target_summary": _target_summary(node),
                    "risk_level": "low",
                }
            )
        return commands
    commands_by_type = {
        "http": [
            ("inspect-http", f"curl -i {health_url}", "Inspect the failing HTTP endpoint directly."),
            ("inspect-logs", "docker logs --tail 100 <container_name>", "Inspect recent container logs for the affected service."),
            ("restart-container", "docker restart <container_name>", "Restart the affected container after confirming it is safe to do so."),
        ],
        "https": [
            ("inspect-https", f"curl -k -i {health_url}", "Inspect the HTTPS endpoint response and TLS behavior."),
            ("restart-service", "sudo systemctl restart raven-web.service", "Restart the web service after inspecting its state."),
        ],
        "api": [
            ("inspect-api", f"curl -i {health_url}", "Check API response details against the expected health output."),
            ("restart-api", "docker restart raven-api", "Restart the API container to restore service."),
        ],
        "ping": [
            ("inspect-network", f"ping -c 4 {node.host}", "Confirm network reachability and packet loss."),
            ("trace-route", f"traceroute {node.host}", "Inspect routing between the runner and the host."),
        ],
    }
    selected = commands_by_type.get(node.health_check_type, commands_by_type["http"])
    return [
        {
            "proposal_id": _unique_proposal_id(f"{node.name}-{key}", existing_ids, f"{incident.id}:{key}"),
            "title": title.replace("-", " ").title(),
            "command": command,
            "rationale": f"{reason} Context: {subject}",
            "execution_mode": node.execution_mode,
            "target_summary": _target_summary(node),
            "risk_level": "medium" if idx else "low",
        }
        for idx, (key, command, reason) in enumerate(selected[:3])
    ]


def _fallback_recommendation(node: Node, incident: Incident, recent_history: list[dict] | None = None, workflow_mode: str = "remediation") -> dict:
    recent_history = recent_history or []
    output_excerpt = _latest_output_excerpt(recent_history)
    summary_prefix = "Root cause investigation" if workflow_mode == "root_cause" else node.name
    summary = f"{summary_prefix} is focused on {incident.failure_type}."
    rationale = "Fallback recommendation generated without a live OpenAI response."
    troubleshooting_steps = [
        "Review the node context and compare it with the current health-check failure.",
        "Inspect the service or container logs nearest the incident start time.",
        "Run the least risky diagnostic command before attempting a restart.",
    ]
    if output_excerpt:
        summary = "I reviewed the latest command output and need one more evidence pass before choosing a remediation."
        rationale = f"The previous command output points to this signal: {output_excerpt[:500]}. I am proposing validation, runtime-state, and log checks to confirm whether the issue is still active."
        troubleshooting_steps = [
            "Compare the latest command output with the current post-validation health status.",
            "Validate the endpoint again to confirm whether the failure is persistent or intermittent.",
            "Inspect runtime state and recent logs to identify what changed after the approved command.",
        ]
    return {
        "suspected_issue_classification": incident.failure_type,
        "summary": summary,
        "troubleshooting_steps": troubleshooting_steps,
        "proposed_commands": _fallback_commands(node, incident, recent_history=recent_history, existing_ids=_previous_proposal_ids(incident)),
        "rationale": rationale,
    }


def _normalize_payload(node: Node, incident: Incident, payload: dict, recent_history: list[dict], workflow_mode: str) -> dict:
    output_excerpt = _latest_output_excerpt(recent_history)
    existing_ids = _previous_proposal_ids(incident)
    proposed = list(payload.get("proposed_commands") or [])
    normalized: list[dict] = []
    for idx, proposal in enumerate(proposed[:3]):
        title = str(proposal.get("title") or f"Follow Up Command {idx + 1}")
        command = str(proposal.get("command") or "")
        if not command:
            continue
        proposal_id = _unique_proposal_id(
            str(proposal.get("proposal_id") or f"{node.name}-{title}"),
            existing_ids,
            f"{incident.id}:{idx}:{title}:{command}:{output_excerpt}",
        )
        normalized.append(
            {
                "proposal_id": proposal_id,
                "title": title,
                "command": command,
                "rationale": str(proposal.get("rationale") or "Follow-up command based on current incident context."),
                "execution_mode": str(proposal.get("execution_mode") or node.execution_mode),
                "target_summary": str(proposal.get("target_summary") or _target_summary(node)),
                "risk_level": str(proposal.get("risk_level") or "low"),
            }
        )

    existing_ids.update(proposal["proposal_id"] for proposal in normalized)
    fallback = _fallback_recommendation(node, incident, recent_history=recent_history, workflow_mode=workflow_mode)
    for proposal in fallback["proposed_commands"]:
        if len(normalized) >= 3:
            break
        proposal = {
            **proposal,
            "proposal_id": _unique_proposal_id(
                proposal["proposal_id"],
                existing_ids,
                f"{incident.id}:fallback:{proposal['proposal_id']}:{output_excerpt}",
            ),
        }
        normalized.append(proposal)

    summary = str(payload.get("summary") or fallback["summary"])
    rationale = str(payload.get("rationale") or fallback["rationale"])
    steps = payload.get("troubleshooting_steps") or fallback["troubleshooting_steps"]
    if output_excerpt and "output" not in summary.lower() and "observ" not in summary.lower():
        summary = f"I reviewed the latest command output. {summary}"
    if output_excerpt and output_excerpt[:120] not in rationale:
        rationale = f"{rationale} Observed command output excerpt: {output_excerpt}"
    if output_excerpt:
        summary = _sentence_limit(summary, max_sentences=2)
        rationale = _sentence_limit(rationale, max_sentences=3)

    return {
        "suspected_issue_classification": str(payload.get("suspected_issue_classification") or fallback["suspected_issue_classification"]),
        "summary": summary,
        "troubleshooting_steps": [str(step) for step in steps][:5],
        "proposed_commands": normalized[:3],
        "rationale": rationale,
    }


class AIRecommendationService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def generate(
        self,
        node: Node,
        incident: Incident,
        recent_history: list[dict],
        prior_incidents: list[dict],
        workflow_mode: str = "remediation",
    ) -> dict:
        if not self.client:
            return _fallback_recommendation(node, incident, recent_history=recent_history, workflow_mode=workflow_mode)

        previous_proposal_ids = sorted(_previous_proposal_ids(incident))
        output_excerpt = _latest_output_excerpt(recent_history, limit=6000)

        prompt = {
            "workflow_mode": workflow_mode,
            "previous_proposal_ids": previous_proposal_ids,
            "latest_command_output_excerpt": output_excerpt,
            "node": {
                "name": node.name,
                "environment": node.environment,
                "host": node.host,
                "port": node.port,
                "url": node.url,
                "health_check_type": node.health_check_type,
                "health_check_path": node.health_check_path,
                "expected_status_code": node.expected_status_code,
                "expected_response_contains": node.expected_response_contains,
                "execution_mode": node.execution_mode,
                "execution_target": node.execution_target,
                "context_text": node.context_text,
                "approved_command_policy": node.approved_command_policy,
            },
            "incident": {
                "failure_type": incident.failure_type,
                "summary": incident.summary,
                "details": incident.details_json,
                "started_at": incident.started_at.isoformat(),
                "last_failure_at": incident.last_failure_at.isoformat(),
            },
            "recent_history": recent_history,
            "prior_incidents": prior_incidents,
            "instructions": [
                "Return strict JSON only.",
                "Initial troubleshooting must be grounded in node.context_text and the incident details.",
                "Keep summary plus rationale concise: 3 to 5 sentences total before the command cards.",
                "For follow-up turns, summary should be 1 to 2 sentences and rationale should be 2 to 3 sentences.",
                "Propose exactly 3 concrete shell commands that the operator can approve individually.",
                "Commands must be safe, single-purpose, and executable by the selected execution_mode.",
                "Do not reuse any previous_proposal_ids.",
                "Use unique proposal_id values that are specific to this turn.",
                "Do not use shell chaining, redirection, heredocs, or multi-command scripts unless explicitly required by approved_command_policy.",
                "Do not propose credential rotation, user management, package installation, or destructive filesystem commands unless approved_command_policy explicitly allows it.",
                "Each proposal must be specific enough to execute exactly as approved.",
            ],
            "response_schema": {
                "suspected_issue_classification": "string",
                "summary": "string",
                "troubleshooting_steps": ["string"],
                "proposed_commands": [
                    {
                        "proposal_id": "string",
                        "title": "string",
                        "command": "string",
                        "rationale": "string",
                        "execution_mode": "agent|runner",
                        "target_summary": "string",
                        "risk_level": "low|medium|high",
                    }
                ],
                "rationale": "string",
            },
        }

        if workflow_mode == "root_cause":
            prompt["instructions"].extend(
                [
                    "The service appears recovered or partially recovered; focus on root cause analysis and prevention.",
                    "Prefer read-only diagnostics and evidence gathering over restart/remediation actions.",
                    "Use prior execution output as primary evidence when proposing the next command.",
                    "Explain what you observe in latest_command_output_excerpt before proposing commands.",
                ]
            )
        else:
            prompt["instructions"].extend(
                [
                    "Use prior execution output to decide whether the next proposed command should diagnose, remediate, or validate.",
                    "For follow-up turns, the summary and rationale must explain what latest_command_output_excerpt indicates.",
                    "Do not simply restate the initial incident summary when command output is available.",
                    "Each command rationale must cite what it is trying to confirm from the prior command output.",
                ]
            )

        try:
            response = self.client.responses.create(
                model=settings.openai_model,
                instructions="You are a cautious SRE assistant for RAVEN. Output strict JSON only.",
                input=json.dumps(prompt),
            )
            payload = _extract_json_payload(response.output_text)
            return _normalize_payload(node, incident, payload, recent_history, workflow_mode)
        except Exception:
            return _fallback_recommendation(node, incident, recent_history=recent_history, workflow_mode=workflow_mode)

    def persist(self, incident: Incident, node: Node, payload: dict) -> AIRecommendation:
        return AIRecommendation(
            incident_id=incident.id,
            node_id=node.id,
            status="generated",
            suspected_issue_classification=payload["suspected_issue_classification"],
            summary=payload["summary"],
            troubleshooting_steps=payload["troubleshooting_steps"],
            proposed_actions=payload["proposed_commands"],
            rationale=payload["rationale"],
            raw_response=json.dumps(payload),
            model_name=settings.openai_model if self.client else "fallback",
        )

    def latest_execution_context(self, node: Node, executions: list[ExecutionTask]) -> list[dict]:
        return [
            {
                "status": task.status,
                "approved_command": task.approved_command,
                "exit_code": task.exit_code,
                "output_excerpt": (task.output or "")[:6000],
                "post_validation_status": task.post_validation_status,
                "queued_at": task.queued_at.isoformat(),
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            }
            for task in executions[:5]
        ]
