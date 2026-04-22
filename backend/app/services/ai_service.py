from __future__ import annotations

import json

from openai import OpenAI

from app.config import get_settings
from app.models import AIRecommendation, Incident, Node
from app.services.remediation_catalog import list_catalog_actions

settings = get_settings()


def _extract_json_payload(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw_text)


def _fallback_recommendation(node: Node, incident: Incident) -> dict:
    default_actions = {
        "ping": ["run_diagnostic_script"],
        "http": ["restart_systemd_service", "curl_validation_check"],
        "https": ["restart_systemd_service", "curl_validation_check"],
        "api": ["restart_container", "curl_validation_check"],
    }
    actions = default_actions.get(node.health_check_type, ["run_diagnostic_script"])
    return {
        "suspected_issue_classification": incident.failure_type,
        "summary": f"{node.name} is failing health checks with {incident.failure_type}.",
        "troubleshooting_steps": [
            "Review recent deployment and infrastructure changes.",
            "Inspect host, service, and application logs around the incident start time.",
            "Validate network reachability and endpoint behavior before remediation.",
        ],
        "proposed_actions": [
            {
                "action_key": action_key,
                "title": action_key.replace("_", " ").title(),
                "reason": "Selected from the approved remediation catalog for this node profile.",
                "priority": "high" if idx == 0 else "medium",
            }
            for idx, action_key in enumerate(actions)
        ],
        "rationale": "Fallback recommendation generated without a live OpenAI response.",
    }


class AIRecommendationService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def generate(self, node: Node, incident: Incident, recent_history: list[dict], prior_incidents: list[dict]) -> dict:
        if not self.client:
            return _fallback_recommendation(node, incident)

        allowed_actions = list_catalog_actions()
        prompt = {
            "node": {
                "name": node.name,
                "environment": node.environment,
                "host": node.host,
                "url": node.url,
                "health_check_type": node.health_check_type,
                "expected_status_code": node.expected_status_code,
                "expected_response_contains": node.expected_response_contains,
                "execution_target": node.execution_target,
                "remediation_profile": node.remediation_profile,
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
            "approved_action_catalog": allowed_actions,
            "instructions": [
                "Return strict JSON only.",
                "Do not invent shell commands or unapproved actions.",
                "Recommend only action_key values from approved_action_catalog.",
                "Keep troubleshooting steps concise and operator-friendly.",
            ],
            "response_schema": {
                "suspected_issue_classification": "string",
                "summary": "string",
                "troubleshooting_steps": ["string"],
                "proposed_actions": [{"action_key": "string", "title": "string", "reason": "string", "priority": "high|medium|low"}],
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
            proposed_actions=payload["proposed_actions"],
            rationale=payload["rationale"],
            raw_response=json.dumps(payload),
            model_name=settings.openai_model if self.client else "fallback",
        )
