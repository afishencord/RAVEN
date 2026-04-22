from __future__ import annotations

import re
from dataclasses import dataclass

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:@/-]+$")


@dataclass(frozen=True)
class ActionDefinition:
    key: str
    title: str
    description: str
    execution_method: str
    command_template: str


CATALOG: dict[str, ActionDefinition] = {
    "restart_systemd_service": ActionDefinition(
        key="restart_systemd_service",
        title="Restart systemd service",
        description="Restarts a predefined Linux service tied to the node execution target.",
        execution_method="local_or_ssh",
        command_template="sudo systemctl restart {target}",
    ),
    "restart_process": ActionDefinition(
        key="restart_process",
        title="Restart managed process",
        description="Restarts a named process through a controlled process manager command.",
        execution_method="local_or_ssh",
        command_template="sudo supervisorctl restart {target}",
    ),
    "restart_container": ActionDefinition(
        key="restart_container",
        title="Restart container",
        description="Restarts a named Docker container tied to the node execution target.",
        execution_method="local_or_ssh",
        command_template="docker restart {target}",
    ),
    "clear_app_cache": ActionDefinition(
        key="clear_app_cache",
        title="Clear application cache",
        description="Runs a predefined cache-clear wrapper for the target application.",
        execution_method="script",
        command_template="/usr/local/bin/raven-clear-cache {target}",
    ),
    "run_diagnostic_script": ActionDefinition(
        key="run_diagnostic_script",
        title="Run diagnostic script",
        description="Runs a predefined diagnostic script from the secure runner allowlist.",
        execution_method="script",
        command_template="/usr/local/bin/raven-diagnostics {target}",
    ),
    "curl_validation_check": ActionDefinition(
        key="curl_validation_check",
        title="Run curl validation check",
        description="Runs a curl validation request against the node health endpoint.",
        execution_method="local",
        command_template="curl -fsS --max-time 10 {url}",
    ),
}


def list_catalog_actions() -> list[dict]:
    return [
        {
            "action_key": action.key,
            "title": action.title,
            "description": action.description,
            "execution_method": action.execution_method,
        }
        for action in CATALOG.values()
    ]


def get_action(action_key: str) -> ActionDefinition:
    if action_key not in CATALOG:
        raise ValueError(f"Unsupported action: {action_key}")
    return CATALOG[action_key]


def validate_target(target: str) -> str:
    if not SAFE_NAME_RE.fullmatch(target):
        raise ValueError("Invalid execution target")
    return target


def validate_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Validation URL must use http or https")
    return url


def render_command(action_key: str, *, target: str, url: str | None = None) -> str:
    action = get_action(action_key)
    if "{url}" in action.command_template:
        return action.command_template.format(url=validate_url(url or ""))
    return action.command_template.format(target=validate_target(target))
