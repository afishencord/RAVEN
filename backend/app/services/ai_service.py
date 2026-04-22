from __future__ import annotations

import json
import re

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


def _fallback_commands(node: Node, incident: Incident) -> list[dict]:
    health_url = build_health_url(node)
    subject = node.context_text or node.execution_target
    commands_by_type = {
        "http": [
            ("inspect-http", f"curl -i {health_url}", "Inspect the failing HTTP endpoint directly."),
            ("inspect-logs", "docker logs --tail 100 raven-test", "Inspect recent container logs for the affected service."),
            ("restart-container", "docker restart raven-test", "Restart the nginx test container to recover from a bad state."),
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
            "proposal_id": f"{_slugify(node.name)}-{key}",
            "title": title.replace("-", " ").title(),
            "command": command,
            "rationale": f"{reason} Context: {subject}",
            "execution_mode": node.execution_mode,
            "target_summary": _target_summary(node),
            "risk_level": "medium" if idx else "low",
        }
        for idx, (key, command, reason) in enumerate(selected[:3])
    ]


def _fallback_recommendation(node: Node, incident: Incident) -> dict:
    return {
        "suspected_issue_classification": incident.failure_type,
        "summary": f"{node.name} is failing health checks with {incident.failure_type}.",
        "troubleshooting_steps": [
            "Review the node context and compare it with the current health-check failure.",
            "Inspect the service or container logs nearest the incident start time.",
            "Run the least risky diagnostic command before attempting a restart.",
        ],
        "proposed_commands": _fallback_commands(node, incident),
        "rationale": "Fallback recommendation generated without a live OpenAI response.",
    }


class AIRecommendationService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def generate(self, node: Node, incident: Incident, recent_history: list[dict], prior_incidents: list[dict]) -> dict:
        if not self.client:
            return _fallback_recommendation(node, incident)

        prompt = {
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
                "Propose up to 3 concrete shell commands that the operator can approve individually.",
                "Commands must be safe, single-purpose, and executable by the selected execution_mode.",
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

        try:
            response = self.client.responses.create(
                model=settings.openai_model,
                instructions="You are a cautious SRE assistant for RAVEN. Output strict JSON only.",
                input=json.dumps(prompt),
            )
            payload = _extract_json_payload(response.output_text)
            proposed = payload.get("proposed_commands") or []
            if not proposed:
                return _fallback_recommendation(node, incident)
            return payload
        except Exception:
            return _fallback_recommendation(node, incident)

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
                "queued_at": task.queued_at.isoformat(),
            }
            for task in executions[:5]
        ]
