export type User = {
  id: number;
  username: string;
  full_name: string;
  role: "viewer" | "operator" | "admin";
  is_active: boolean;
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
  remediation_profile: string;
  execution_target: string;
  is_enabled: boolean;
  current_status: string;
  last_check_at?: string | null;
  last_incident_at?: string | null;
  created_at: string;
  updated_at: string;
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
  is_active: boolean;
};

export type Recommendation = {
  id: number;
  status: string;
  suspected_issue_classification: string;
  summary: string;
  troubleshooting_steps: string[];
  proposed_actions: Array<{ action_key: string; title: string; reason: string; priority?: string }>;
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
  profile_id: number;
  action_key: string;
  target: string;
  parameters: Record<string, unknown>;
  execution_method: string;
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

export type RemediationProfile = {
  id: number;
  name: string;
  description: string;
  allowed_action_keys: string[];
  allowed_targets: string[];
  approval_required: boolean;
  cooldown_seconds: number;
  retry_limit: number;
  post_action_validation: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type NodeDetail = {
  node: NodeRecord;
  health_checks: HealthCheck[];
  incidents: Incident[];
  recommendations: Recommendation[];
  executions: ExecutionTask[];
  remediation_profile?: RemediationProfile | null;
};

export type MessageIncident = {
  incident: Incident;
  node: NodeRecord;
  latest_recommendation?: Recommendation | null;
  notes: IncidentNote[];
  executions: ExecutionTask[];
};
