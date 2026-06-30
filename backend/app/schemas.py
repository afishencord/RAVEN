from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class PlatformSettingsBase(BaseModel):
    organizationName: str = "Acme Corporation"
    modelProvider: str = "env_default"
    customModel: str = "gpt-5.2"
    modelEndpoint: str = ""
    localAuthEnabled: bool = True
    ldapEnabled: bool = False
    ssoEnabled: bool = False
    ldapUrl: str = ""
    ldapBindDn: str = ""
    ldapBaseDn: str = ""
    ldapUserSearchBase: str = ""
    ldapGroupSearchBase: str = ""
    ldapUserFilter: str = ""
    ldapGroupFilter: str = ""
    ldapLoginAttribute: str = ""
    ldapEmailAttribute: str = ""
    ldapNameAttribute: str = ""
    ldapMembershipAttribute: str = ""
    ssoIssuer: str = ""
    ssoClientId: str = ""
    alertEmail: str = "ops@example.com"
    webhookUrl: str = ""
    retentionDays: int = Field(default=180, ge=1)
    auditRetentionDays: int = Field(default=365, ge=1)
    approvalMode: str = "Operator approval required"
    maintenanceWindow: str = "Sunday 02:00-04:00"
    requirePostValidation: bool = True
    notifyOnResolution: bool = True
    notifyOnLicenseWarning: bool = True
    allowRunnerExecution: bool = True


class PlatformSettingsRead(PlatformSettingsBase):
    updated_at: datetime | None = None


class PlatformSettingsUpdate(BaseModel):
    organizationName: str | None = None
    modelProvider: str | None = None
    customModel: str | None = None
    modelEndpoint: str | None = None
    localAuthEnabled: bool | None = None
    ldapEnabled: bool | None = None
    ssoEnabled: bool | None = None
    ldapUrl: str | None = None
    ldapBindDn: str | None = None
    ldapBaseDn: str | None = None
    ldapUserSearchBase: str | None = None
    ldapGroupSearchBase: str | None = None
    ldapUserFilter: str | None = None
    ldapGroupFilter: str | None = None
    ldapLoginAttribute: str | None = None
    ldapEmailAttribute: str | None = None
    ldapNameAttribute: str | None = None
    ldapMembershipAttribute: str | None = None
    ssoIssuer: str | None = None
    ssoClientId: str | None = None
    alertEmail: str | None = None
    webhookUrl: str | None = None
    retentionDays: int | None = Field(default=None, ge=1)
    auditRetentionDays: int | None = Field(default=None, ge=1)
    approvalMode: str | None = None
    maintenanceWindow: str | None = None
    requirePostValidation: bool | None = None
    notifyOnResolution: bool | None = None
    notifyOnLicenseWarning: bool | None = None
    allowRunnerExecution: bool | None = None


class CredentialBase(BaseModel):
    name: str
    kind: str
    username: str | None = None
    description: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class CredentialCreate(CredentialBase):
    secret_value: str = Field(min_length=1)


class CredentialUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    username: str | None = None
    description: str | None = None
    metadata_json: dict | None = None
    secret_value: str | None = None


class CredentialRead(CredentialBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    has_secret: bool
    masked_secret: str
    created_at: datetime
    updated_at: datetime


class FlockPolicyBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    is_default: bool = False
    is_enabled: bool = True
    heartbeat_interval_seconds: int = 10
    task_timeout_seconds: int = 60
    command_allowlist: list[str] = Field(default_factory=list)


class FlockPolicyCreate(FlockPolicyBase):
    pass


class FlockPolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
    is_enabled: bool | None = None
    heartbeat_interval_seconds: int | None = None
    task_timeout_seconds: int | None = None
    command_allowlist: list[str] | None = None


class FlockPolicyRead(FlockPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_count: int = 0
    created_at: datetime
    updated_at: datetime


class FlockAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    name: str
    hostname: str
    platform: str
    architecture: str
    version: str
    policy_id: int | None
    policy_name: str | None = None
    enrollment_token_id: int | None
    node_id: int | None = None
    status: str
    last_seen_at: datetime | None
    enrolled_at: datetime
    unenrolled_at: datetime | None = None
    metadata_json: dict
    latest_metrics: dict | None = None
    pending_task_count: int = 0
    created_at: datetime
    updated_at: datetime


class FlockAgentUpdate(BaseModel):
    policy_id: int | None = None
    status: str | None = None


class FlockEnrollmentRequest(BaseModel):
    enrollment_token: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    platform: str = "linux"
    architecture: str = "unknown"
    version: str = "dev"
    metadata_json: dict = Field(default_factory=dict)


class FlockEnrollmentResponse(BaseModel):
    agent_id: str
    agent_token: str
    policy: FlockPolicyRead


class FlockHeartbeatRequest(BaseModel):
    hostname: str | None = None
    platform: str | None = None
    architecture: str | None = None
    version: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    metrics_json: dict = Field(default_factory=dict)


class FlockHeartbeatResponse(BaseModel):
    status: str
    policy: FlockPolicyRead


class FlockClaimedTaskRead(BaseModel):
    id: int
    task_type: str = "command"
    command: str
    timeout_seconds: int


class FlockTaskResultRequest(BaseModel):
    exit_code: int
    output: str = ""


class FlockDispatchRequest(BaseModel):
    target: str = Field(min_length=1)
    command: str = Field(min_length=1)
    execution_task_id: int | None = None
    timeout_seconds: int = 60


class FlockDispatchResponse(BaseModel):
    status: str
    exit_code: int
    output: str
    agent_id: str | None = None
    task_id: int | None = None


class FlockUnenrollResponse(BaseModel):
    status: str
    agent_id: str
    node_id: int | None = None
    task_id: int | None = None


class FlockMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    payload_json: dict
    collected_at: datetime


class NodeHealthCheckBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    check_type: str = Field(min_length=1, max_length=32)
    config_json: dict = Field(default_factory=dict)
    interval_seconds: int = 60
    timeout_seconds: int = 5
    retry_count: int = 3
    is_enabled: bool = True
    sort_order: int = 0


class NodeHealthCheckCreate(NodeHealthCheckBase):
    pass


class NodeHealthCheckUpdate(BaseModel):
    name: str | None = None
    check_type: str | None = None
    config_json: dict | None = None
    interval_seconds: int | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None


class NodeHealthCheckRead(NodeHealthCheckBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    current_status: str
    consecutive_failures: int
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_latency_ms: int | None
    last_http_status: int | None
    last_error_type: str | None
    last_error_detail: str | None
    last_response_excerpt: str | None
    created_at: datetime
    updated_at: datetime


class NodeHealthCheckReplaceRequest(BaseModel):
    health_checks: list[NodeHealthCheckCreate] = Field(default_factory=list)


class NodeBase(BaseModel):
    name: str
    description: str | None = None
    environment: str = "prod"
    host: str
    port: int | None = None
    url: str | None = None
    health_check_type: str = "http"
    health_check_path: str | None = None
    expected_status_code: int = 200
    expected_response_contains: str | None = None
    check_interval_seconds: int = 60
    timeout_seconds: int = 5
    retry_count: int = 3
    execution_mode: str = "runner"
    execution_target: str
    group_name: str | None = None
    context_text: str | None = None
    approved_command_policy: str | None = None
    credential_id: int | None = None
    is_enabled: bool = True


class NodeCreate(NodeBase):
    pass


class NodeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    environment: str | None = None
    host: str | None = None
    port: int | None = None
    url: str | None = None
    health_check_type: str | None = None
    health_check_path: str | None = None
    expected_status_code: int | None = None
    expected_response_contains: str | None = None
    check_interval_seconds: int | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    execution_mode: str | None = None
    execution_target: str | None = None
    group_name: str | None = None
    context_text: str | None = None
    approved_command_policy: str | None = None
    credential_id: int | None = None
    is_enabled: bool | None = None


class NodeRead(NodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_status: str
    last_check_at: datetime | None
    last_incident_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NodeGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class NodeGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class MetricBreakdownItem(BaseModel):
    label: str
    value: int


class TimeSeriesPoint(BaseModel):
    date: str
    value: int


class DashboardMetricsRead(BaseModel):
    total_nodes: int
    enabled_nodes: int
    active_incidents: int
    resolved_incidents: int
    successful_remediations: int
    average_resolution_minutes: float | None
    node_state_counts: list[MetricBreakdownItem]
    execution_status_counts: list[MetricBreakdownItem]
    approval_decision_counts: list[MetricBreakdownItem]
    execution_mode_counts: list[MetricBreakdownItem]
    environment_counts: list[MetricBreakdownItem]
    failure_type_counts: list[MetricBreakdownItem]
    successful_remediations_over_time: list[TimeSeriesPoint]


class HealthCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    health_check_id: int | None = None
    check_name: str | None = None
    check_type: str | None = None
    status: str
    success: bool
    latency_ms: int | None
    http_status: int | None
    error_type: str | None
    error_detail: str | None
    response_excerpt: str | None
    checked_at: datetime


class CommandProposalRead(BaseModel):
    proposal_id: str
    title: str
    command: str
    rationale: str
    execution_mode: str
    target_summary: str
    risk_level: str


class AIRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    suspected_issue_classification: str
    summary: str
    troubleshooting_steps: list[str]
    proposed_commands: list[CommandProposalRead] = Field(validation_alias="proposed_actions")
    rationale: str
    model_name: str
    created_at: datetime


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    status: str
    severity: str
    failure_type: str
    summary: str
    details_json: dict
    started_at: datetime
    last_failure_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    archived_at: datetime | None
    is_active: bool


class IncidentNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2_000)


class IncidentNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    user_id: int
    note: str
    created_at: datetime


class RemediationProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    allowed_action_keys: list[str]
    allowed_targets: list[str]
    approval_required: bool
    cooldown_seconds: int
    retry_limit: int
    post_action_validation: dict
    created_at: datetime
    updated_at: datetime


class ValidationDefinitionBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    validation_type: str = "http"
    command: str | None = None
    url: str | None = None
    path: str | None = None
    expected_status_code: int | None = 200
    expected_exit_code: int = 0
    expected_response_contains: str | None = None
    timeout_seconds: int = 10
    is_enabled: bool = True


class ValidationDefinitionCreate(ValidationDefinitionBase):
    pass


class ValidationDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    validation_type: str | None = None
    command: str | None = None
    url: str | None = None
    path: str | None = None
    expected_status_code: int | None = None
    expected_exit_code: int | None = None
    expected_response_contains: str | None = None
    timeout_seconds: int | None = None
    is_enabled: bool | None = None


class ValidationDefinitionRead(ValidationDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assigned_node_count: int = 0
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RemediationDefinitionBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    command: str = Field(min_length=1)
    risk_level: str = "medium"
    execution_mode: str | None = None
    is_enabled: bool = True


class RemediationDefinitionCreate(RemediationDefinitionBase):
    pass


class RemediationDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    command: str | None = None
    risk_level: str | None = None
    execution_mode: str | None = None
    is_enabled: bool | None = None


class RemediationDefinitionRead(RemediationDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assigned_node_count: int = 0
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ValidationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    incident_id: int | None
    validation_id: int
    validation_name: str | None = None
    status: str
    matched_expectation: bool
    observed_status_code: int | None
    observed_exit_code: int | None
    output: str | None
    error_detail: str | None
    started_at: datetime
    finished_at: datetime | None


class NodeValidationAssignmentRead(BaseModel):
    id: int
    node_id: int
    validation_id: int
    is_enabled: bool
    sort_order: int
    validation: ValidationDefinitionRead


class NodeRemediationAssignmentRead(BaseModel):
    id: int
    node_id: int
    remediation_id: int
    is_enabled: bool
    sort_order: int
    remediation: RemediationDefinitionRead


class NodeAutomationEdgeRead(BaseModel):
    id: int
    node_id: int
    validation_id: int
    remediation_id: int
    is_enabled: bool
    sort_order: int


class NodeAutomationEdgeUpdate(BaseModel):
    validation_id: int
    remediation_id: int


class NodeAutomationAssignmentsRead(BaseModel):
    node_id: int
    validations: list[NodeValidationAssignmentRead]
    remediations: list[NodeRemediationAssignmentRead]
    edges: list[NodeAutomationEdgeRead] = Field(default_factory=list)


class NodeAutomationAssignmentsUpdate(BaseModel):
    validation_ids: list[int] = Field(default_factory=list)
    remediation_ids: list[int] = Field(default_factory=list)
    edges: list[NodeAutomationEdgeUpdate] = Field(default_factory=list)


class ValidationTestRequest(BaseModel):
    node_id: int | None = None


class RemediationPreviewRead(BaseModel):
    remediation_id: int
    command: str
    execution_mode: str | None
    risk_level: str


class ExecutionTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    node_id: int
    proposal_id: str | None
    proposal_title: str | None
    target: str
    parameters: dict
    execution_method: str
    execution_mode: str
    approved_command: str | None
    command_preview: str
    status: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    output: str | None
    post_validation_status: str | None
    retry_count: int
    requested_by_id: int
    approved_by_id: int


class ApprovalDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    recommendation_id: int | None
    execution_task_id: int | None
    action_key: str
    decision: str
    note: str | None
    decided_by_id: int
    decided_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    entity_type: str
    entity_id: str
    action: str
    details_json: dict
    created_at: datetime


class NodeDetailRead(BaseModel):
    node: NodeRead
    health_checks: list[HealthCheckRead]
    health_check_definitions: list[NodeHealthCheckRead] = Field(default_factory=list)
    incidents: list[IncidentRead]
    recommendations: list[AIRecommendationRead]
    executions: list[ExecutionTaskRead]
    approvals: list[ApprovalDecisionRead]
    credential: CredentialRead | None = None


class IncidentActionRequest(BaseModel):
    proposal_id: str | None = None
    note: str | None = None


class MessageIncidentRead(BaseModel):
    incident: IncidentRead
    node: NodeRead
    latest_recommendation: AIRecommendationRead | None
    recommendations: list[AIRecommendationRead]
    validation_runs: list[ValidationRunRead] = Field(default_factory=list)
    notes: list[IncidentNoteRead]
    executions: list[ExecutionTaskRead]
    approvals: list[ApprovalDecisionRead]


class StatusResponse(BaseModel):
    status: str
