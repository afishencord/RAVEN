export type User = {
  id: number;
  username: string;
  full_name: string;
  role: "viewer" | "operator" | "admin";
  is_active: boolean;
};

export type CredentialRecord = {
  id: number;
  name: string;
  kind: string;
  username?: string | null;
  description?: string | null;
  metadata_json: Record<string, unknown>;
  has_secret: boolean;
  masked_secret: string;
  created_at: string;
  updated_at: string;
};

export type NodeRecord = {
  id: number;
  name: string;
  description?: string | null;
  environment: string;
  host: string;
  port?: number | null;
  url?: string | null;
  health_check_type: string;
  health_check_path?: string | null;
  expected_status_code: number;
  expected_response_contains?: string | null;
  check_interval_seconds: number;
  timeout_seconds: number;
  retry_count: number;
  execution_mode: "runner" | "agent";
  execution_target: string;
  group_name?: string | null;
  context_text?: string | null;
  approved_command_policy?: string | null;
  credential_id?: number | null;
  is_enabled: boolean;
  current_status: string;
  last_check_at?: string | null;
  last_incident_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type NodeGroupRecord = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
};

export type MetricBreakdownItem = {
  label: string;
  value: number;
};

export type TimeSeriesPoint = {
  date: string;
  value: number;
};

export type DashboardMetrics = {
  total_nodes: number;
  enabled_nodes: number;
  active_incidents: number;
  resolved_incidents: number;
  successful_remediations: number;
  average_resolution_minutes: number | null;
  node_state_counts: MetricBreakdownItem[];
  execution_status_counts: MetricBreakdownItem[];
  approval_decision_counts: MetricBreakdownItem[];
  execution_mode_counts: MetricBreakdownItem[];
  environment_counts: MetricBreakdownItem[];
  failure_type_counts: MetricBreakdownItem[];
  successful_remediations_over_time: TimeSeriesPoint[];
};

export type HealthCheck = {
  id: number;
  status: string;
  success: boolean;
  latency_ms?: number | null;
  http_status?: number | null;
  error_type?: string | null;
  error_detail?: string | null;
  response_excerpt?: string | null;
  checked_at: string;
};

export type Incident = {
  id: number;
  node_id: number;
  status: string;
  severity: string;
  failure_type: string;
  summary: string;
  details_json: Record<string, unknown>;
  started_at: string;
  last_failure_at: string;
  resolved_at?: string | null;
  acknowledged_at?: string | null;
  archived_at?: string | null;
  is_active: boolean;
};

export type CommandProposal = {
  proposal_id: string;
  title: string;
  command: string;
  rationale: string;
  execution_mode: "runner" | "agent";
  target_summary: string;
  risk_level: string;
};

export type Recommendation = {
  id: number;
  status: string;
  suspected_issue_classification: string;
  summary: string;
  troubleshooting_steps: string[];
  proposed_commands: CommandProposal[];
  rationale: string;
  model_name: string;
  created_at: string;
};

export type IncidentNote = {
  id: number;
  incident_id: number;
  user_id: number;
  note: string;
  created_at: string;
};

export type ExecutionTask = {
  id: number;
  incident_id: number;
  node_id: number;
  proposal_id?: string | null;
  proposal_title?: string | null;
  target: string;
  parameters: Record<string, unknown>;
  execution_method: string;
  execution_mode: string;
  approved_command?: string | null;
  command_preview: string;
  status: string;
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  exit_code?: number | null;
  output?: string | null;
  post_validation_status?: string | null;
  retry_count: number;
  requested_by_id: number;
  approved_by_id: number;
};

export type ApprovalDecision = {
  id: number;
  incident_id: number;
  recommendation_id?: number | null;
  execution_task_id?: number | null;
  action_key: string;
  decision: string;
  note?: string | null;
  decided_by_id: number;
  decided_at: string;
};

export type NodeDetail = {
  node: NodeRecord;
  health_checks: HealthCheck[];
  incidents: Incident[];
  recommendations: Recommendation[];
  executions: ExecutionTask[];
  approvals: ApprovalDecision[];
  credential?: CredentialRecord | null;
};

export type MessageIncident = {
  incident: Incident;
  node: NodeRecord;
  latest_recommendation?: Recommendation | null;
  recommendations: Recommendation[];
  notes: IncidentNote[];
  executions: ExecutionTask[];
  approvals: ApprovalDecision[];
};
