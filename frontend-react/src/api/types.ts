/**
 * Prism v2 — API Type Definitions
 * Generated from backend/app/schemas/*.py
 */

// ---------------------------------------------------------------------------
// Common envelope types
// ---------------------------------------------------------------------------

export interface ErrorDetail {
  code: string;
  message: string;
}

export interface ApiEnvelope<T> {
  data: T;
  error: ErrorDetail | null;
}

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  username: string;
  role: string;
  avatar_url: string | null;
  last_login_at: string | null;
  created_at: string;
  phone: string | null;
  email_verified: boolean;
  has_google: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface DevDefaultAdmin {
  email: string;
  password: string;
}

export interface AuthProvidersResponse {
  email_password: boolean;
  email_magic: boolean;
  email_otp: boolean;
  phone_password: boolean;
  google: boolean;
  dev_default_admin: DevDefaultAdmin | null;
}

export interface AuthConfigEntry {
  key: string;
  value_json: unknown;
  updated_at: string | null;
  updated_by: string | null;
}

export interface SSETicketResponse {
  ticket: string;
}

// ---------------------------------------------------------------------------
// Session types
// ---------------------------------------------------------------------------

export interface Session {
  id: string;
  title: string | null;
  status: 'idle' | 'running' | 'queued';
  blocking_run_id: string | null;
  config_snapshot: Record<string, unknown>;
  is_pinned: boolean;
  pinned_at: string | null;
  im_channel: string | null;
  im_chat_id: string | null;
  message_count: number;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionListItem {
  id: string;
  title: string | null;
  status: 'idle' | 'running' | 'queued';
  is_pinned: boolean;
  last_message_preview: string | null;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Message types
// ---------------------------------------------------------------------------

export interface ContentBlock {
  type: 'text' | 'tool_use' | 'thinking';
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  input?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface Message {
  id: string;
  run_id: string | null;
  role: 'user' | 'assistant' | 'tool_use' | 'tool_result' | 'system';
  content: ContentBlock[];
  text_preview: string | null;
  sequence_no: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Run types
// ---------------------------------------------------------------------------

export interface Run {
  id: string;
  session_id: string;
  prompt: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timeout';
  model: string;
  provider_id: string | null;
  schedule_mode: string;
  agent_type: string | null;
  error_message: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  turn_count: number | null;
  harness_summary: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface RunListItem {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timeout';
  prompt: string;
  agent_type: string | null;
  turn_count: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Provider types
// ---------------------------------------------------------------------------

export interface ProviderCapabilities {
  prompt_cache: boolean;
  streaming_tools: boolean;
  extended_thinking: boolean;
  vision: boolean;
}

export interface Provider {
  id: string;
  scope: string;
  name: string;
  protocol: string;
  base_url: string;
  api_key_masked: string;
  model_id: string;
  is_default: boolean;
  priority: number;
  is_healthy: boolean;
  config: Record<string, unknown>;
  user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderPreset {
  name: string;
  protocol: 'anthropic' | 'openai';
  base_url: string;
  model_id: string;
  description: string;
  capabilities: ProviderCapabilities;
}

export interface TestProviderResponse {
  success: boolean;
  latency_ms: number | null;
  error: string | null;
  detected_capabilities: ProviderCapabilities | null;
}

// ---------------------------------------------------------------------------
// MCP types
// ---------------------------------------------------------------------------

export interface McpServer {
  id: string;
  name: string;
  description: string | null;
  transport: 'stdio' | 'http';
  command: string | null;
  args: string[];
  env: Record<string, string>;
  url: string | null;
  headers: Record<string, string> | null;
  scope: string;
  created_at: string;
}

export interface MCPInstall {
  id: string;
  mcp_server_id: string;
  mcp_server_name: string;
  is_enabled: boolean;
  config_override: Record<string, unknown>;
  created_at: string;
}

export interface MCPTestResponse {
  success: boolean;
  server_id: string;
  detected_capabilities: string[];
  error: string | null;
}

// ---------------------------------------------------------------------------
// Skills types
// ---------------------------------------------------------------------------

export interface SkillPackage {
  name: string;
  description: string;
  version: string;
  source: 'local' | 'github' | 'marketplace' | 'context7';
  source_url: string;
  author: string | null;
  tags: string[];
  stars: number;
  installed: boolean;
  installed_version: string | null;
  marketplace_id: string | null;
  plugin_name: string | null;
  homepage: string | null;
  repository: string | null;
  license: string | null;
  readme_available: boolean;
}

export interface SkillInstall {
  id: string;
  user_id: string;
  skill_name: string;
  source: string;
  source_url: string | null;
  version: string;
  installed_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  marketplace_id: string | null;
}

export interface SkillContent {
  name: string;
  content: string;
  [key: string]: unknown;
}

export interface SkillReadme {
  name: string;
  readme: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Plugin types
// ---------------------------------------------------------------------------

export interface PluginLibraryItem {
  id: string;
  name: string;
  version: string;
  description: string;
  type: string;
  enabled: boolean;
  manifest_yaml: string | null;
  manifest_json: Record<string, unknown> | null;
  permissions: string[];
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Marketplace types
// ---------------------------------------------------------------------------

export interface MarketplaceOwner {
  name: string;
  email: string | null;
}

export interface MarketplacePluginEntry {
  name: string;
  description: string | null;
  version: string | null;
  source: string | Record<string, unknown> | null;
  extra: Record<string, unknown>;
}

export interface Marketplace {
  id: string;
  url: string;
  name: string;
  catalog_json: Record<string, unknown> | null;
  plugin_count: number;
  last_fetched_at: string | null;
  created_by: string;
  created_at: string;
}

export interface InstallReport {
  plugin_name: string;
  installed_skills: string[];
  failures: Array<{ skill_dir: string; error: string }>;
}

// ---------------------------------------------------------------------------
// IM types
// ---------------------------------------------------------------------------

export interface IMChannel {
  id: string;
  channel: string;
  is_enabled: boolean;
  config: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface IMBinding {
  id: string;
  user_id: string;
  channel: string;
  platform_user_id: string;
  platform_chat_id: string;
  display_name: string | null;
  paired_at: string | null;
  created_at: string;
}

export interface PairingCodeResponse {
  pairing_code: string;
  channel: string;
  expires_at: string;
}

// ---------------------------------------------------------------------------
// Admin types
// ---------------------------------------------------------------------------

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  role: string;
  last_login_at: string | null;
  created_at: string;
}

export interface InviteCode {
  id: string;
  code: string;
  created_by: string;
  max_uses: number;
  used_count: number;
  expires_at: string | null;
  is_valid: boolean;
  created_at: string;
}

export interface AuditLog {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  severity: string;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export interface SystemStats {
  runs_24h: number;
  runs_7d: number;
  cost_usd_7d: number;
  cache_savings_usd_7d: number;
  harness_events_24h: Record<string, number>;
  active_sessions: number;
  active_users_24h: number;
  component_health: Record<string, string>;
  timestamp: string;
}

export interface UsageStat {
  group_by: string;
  [key: string]: unknown;
}

export interface AlertConfig {
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Task types
// ---------------------------------------------------------------------------

export interface SubmitTaskResponse {
  session_id: string;
  run_id: string | null;
  accepted_type: string;
  queue_position: number | null;
}

// ---------------------------------------------------------------------------
// SSE types
// ---------------------------------------------------------------------------

export type SSEEventType =
  | 'text_delta'
  | 'tool_use_delta'
  | 'tool_start'
  | 'tool_end'
  | 'message_complete'
  | 'run_complete'
  | 'run_error'
  | 'run_crashed'
  | 'permission_ask'
  | 'harness_event'
  | 'coordinator_plan_update'
  | 'session_title'
  | 'queue_update'
  | 'compaction'
  | 'message';

export interface SSEEvent {
  type: SSEEventType;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Error reporting types
// ---------------------------------------------------------------------------

export interface ErrorReport {
  message?: string;
  stack?: string;
  name?: string;
  url?: string;
  context?: Record<string, unknown>;
  severity?: 'info' | 'warning' | 'error' | 'critical';
}

// ---------------------------------------------------------------------------
// Health types
// ---------------------------------------------------------------------------

export interface HealthDetailed {
  status: string;
  components: Record<string, unknown>;
  [key: string]: unknown;
}
