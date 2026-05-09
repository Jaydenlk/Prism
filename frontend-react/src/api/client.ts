/**
 * Prism v2 — Typed API Client
 * Ported from frontend/apiClient.js — full TypeScript port with named exports.
 *
 * Auth flow:
 *   - access_token stored in sessionStorage (cleared on tab close)
 *   - refresh_token is HttpOnly cookie managed by browser
 *   - 401 → auto-refresh → retry; still 401 → dispatch prism:unauthorized
 *
 * Envelope: backend wraps all responses as { data: <payload>, error: null }
 *   request() unwraps to .data automatically.
 */

import type {
  User,
  TokenResponse,
  AuthProvidersResponse,
  Session,
  SessionListItem,
  Message,
  Run,
  RunListItem,
  Provider,
  ProviderPreset,
  TestProviderResponse,
  McpServer,
  MCPInstall,
  MCPTestResponse,
  SkillPackage,
  SkillInstall,
  SkillContent,
  SkillReadme,
  PluginLibraryItem,
  Marketplace,
  InstallReport,
  IMChannel,
  IMBinding,
  PairingCodeResponse,
  AdminUser,
  InviteCode,
  AuditLog,
  SystemStats,
  SubmitTaskResponse,
  SSEEvent,
  SSEEventType,
  ErrorReport,
  HealthDetailed,
  PagedResponse,
  SSETicketResponse,
} from './types';

declare global {
  interface Window {
    PRISM_API_BASE?: string;
  }
}

// ---------------------------------------------------------------------------
// Internal constants
// ---------------------------------------------------------------------------

const API_BASE = ((window.PRISM_API_BASE ?? '/api/v1')).replace(/\/$/, '');

const TOKEN_KEY = 'prism_access_token';
const USER_KEY = 'prism_current_user';

// ---------------------------------------------------------------------------
// Typed error class
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

function storeToken(token: string | null): void {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

function storeUser(user: User | null): void {
  if (user) sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  else sessionStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export function currentUser(): User | null {
  const raw = sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Base fetch wrapper
// ---------------------------------------------------------------------------

let _refreshing: Promise<boolean> | null = null;

export interface RequestOpts {
  json?: unknown;
  query?: Record<string, string | number | undefined | null>;
}

async function fetchRaw(
  method: string,
  path: string,
  opts: RequestOpts = {},
  skipRefresh = false,
): Promise<Response> {
  let url = API_BASE + path;
  if (opts.query) {
    const params = new URLSearchParams(
      Object.fromEntries(
        Object.entries(opts.query)
          .filter(([, v]) => v !== undefined && v !== null)
          .map(([k, v]) => [k, String(v)]),
      ),
    );
    url += '?' + params.toString();
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const init: RequestInit = {
    method: method.toUpperCase(),
    headers,
    credentials: 'include',
  };
  if (opts.json !== undefined) init.body = JSON.stringify(opts.json);

  const res = await fetch(url, init);

  const _noRefreshPaths = ['/auth/login', '/auth/register', '/auth/refresh'];
  const isAuthPath = _noRefreshPaths.some(p => path === p || path.startsWith(p + '?'));

  if (res.status === 401 && !skipRefresh && !isAuthPath) {
    if (!_refreshing) {
      _refreshing = doRefresh().finally(() => {
        _refreshing = null;
      });
    }
    const ok = await _refreshing;
    if (ok) {
      return fetchRaw(method, path, opts, true);
    } else {
      storeToken(null);
      storeUser(null);
      window.dispatchEvent(new CustomEvent('prism:unauthorized'));
      throw new ApiError('Unauthorized', 401);
    }
  }

  return res;
}

async function doRefresh(): Promise<boolean> {
  try {
    const res = await fetch(API_BASE + '/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return false;
    const body = (await res.json()) as unknown;
    const data =
      body !== null &&
      typeof body === 'object' &&
      'data' in (body as object)
        ? (body as { data: unknown }).data
        : body;
    if (
      data !== null &&
      typeof data === 'object' &&
      'access_token' in (data as object)
    ) {
      storeToken((data as { access_token: string }).access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Generic request helpers
// ---------------------------------------------------------------------------

export async function request<T>(
  method: string,
  path: string,
  opts: RequestOpts = {},
): Promise<T> {
  const res = await fetchRaw(method, path, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as unknown;
      if (
        body !== null &&
        typeof body === 'object' &&
        'detail' in (body as object)
      ) {
        const d = (body as { detail: unknown }).detail;
        detail = typeof d === 'string' ? d : JSON.stringify(d);
      } else if (
        body !== null &&
        typeof body === 'object' &&
        'error' in (body as object)
      ) {
        const e = (body as { error: unknown }).error;
        detail = typeof e === 'string' ? e : JSON.stringify(e);
      }
    } catch { /* non-JSON error body */ }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return null as unknown as T;
  try {
    const body = (await res.json()) as unknown;
    if (
      body !== null &&
      typeof body === 'object' &&
      'data' in (body as object) &&
      'error' in (body as object)
    ) {
      return (body as { data: T }).data;
    }
    return body as T;
  } catch {
    return null as unknown as T;
  }
}

export async function requestBlob(
  method: string,
  path: string,
  opts: RequestOpts = {},
  filename = 'download',
): Promise<Blob> {
  const res = await fetchRaw(method, path, opts);
  if (!res.ok) {
    throw new ApiError(`HTTP ${res.status}`, res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 1000);
  return blob;
}

// ---------------------------------------------------------------------------
// Auth functions
// ---------------------------------------------------------------------------

export async function login(
  email: string,
  password: string,
): Promise<{ user: User; access_token: string }> {
  const data = await request<TokenResponse>('POST', '/auth/login', {
    json: { email, password },
  });
  storeToken(data.access_token);
  const user = await me();
  return { user, access_token: data.access_token };
}

export async function register(params: {
  email: string;
  username: string;
  password: string;
  invite_code?: string;
}): Promise<TokenResponse> {
  return request<TokenResponse>('POST', '/auth/register', { json: params });
}

export async function refresh(): Promise<boolean> {
  return doRefresh();
}

export async function logout(): Promise<void> {
  try {
    await request<null>('POST', '/auth/logout');
  } catch { /* best-effort */ }
  storeToken(null);
  storeUser(null);
}

export async function me(): Promise<User> {
  const user = await request<User>('GET', '/auth/me');
  storeUser(user);
  return user;
}

export async function createSSETicket(
  session_id: string,
): Promise<SSETicketResponse> {
  return request<SSETicketResponse>('POST', '/auth/sse-ticket', {
    json: { session_id },
  });
}

export async function authProviders(): Promise<AuthProvidersResponse> {
  return request<AuthProvidersResponse>('GET', '/auth/providers');
}

export async function emailMagicRequest(params: {
  email: string;
}): Promise<null> {
  return request<null>('POST', '/auth/email-magic/request', { json: params });
}

export async function emailMagicVerify(params: {
  challenge_id: string;
  token: string;
}): Promise<TokenResponse> {
  const data = await request<TokenResponse>('POST', '/auth/email-magic/verify', {
    json: params,
  });
  if (data && data.access_token) storeToken(data.access_token);
  return data;
}

export async function emailOtpRequest(params: {
  email: string;
}): Promise<null> {
  return request<null>('POST', '/auth/email-otp/request', { json: params });
}

export async function emailOtpVerify(params: {
  email: string;
  code: string;
}): Promise<TokenResponse> {
  const data = await request<TokenResponse>('POST', '/auth/email-otp/verify', {
    json: params,
  });
  if (data && data.access_token) storeToken(data.access_token);
  return data;
}

export async function forgotPassword(params: { email: string }): Promise<null> {
  return request<null>('POST', '/auth/forgot-password', { json: params });
}

export async function resetPassword(params: {
  challenge_id: string;
  token: string;
  new_password: string;
}): Promise<null> {
  return request<null>('POST', '/auth/reset-password', { json: params });
}

export async function changePassword(params: {
  current_password: string;
  new_password: string;
}): Promise<null> {
  return request<null>('POST', '/auth/change-password', { json: params });
}

export async function phoneRegister(params: {
  phone: string;
  password: string;
  invite_code?: string;
}): Promise<TokenResponse> {
  const data = await request<TokenResponse>('POST', '/auth/phone-register', {
    json: params,
  });
  if (data && data.access_token) storeToken(data.access_token);
  return data;
}

export async function phoneLogin(params: {
  phone: string;
  password: string;
}): Promise<TokenResponse> {
  const data = await request<TokenResponse>('POST', '/auth/phone-login', {
    json: params,
  });
  if (data && data.access_token) storeToken(data.access_token);
  return data;
}

export async function googleComplete(params: {
  tmp_token: string;
  invite_code?: string;
}): Promise<TokenResponse> {
  const data = await request<TokenResponse>('POST', '/auth/google/complete', {
    json: params,
  });
  if (data && data.access_token) storeToken(data.access_token);
  return data;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function healthDetailed(): Promise<HealthDetailed> {
  return request<HealthDetailed>('GET', '/health/detailed');
}

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export interface SSEHandlers {
  onEvent?: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
}

const SSE_EVENT_TYPES: SSEEventType[] = [
  'text_delta',
  'tool_use_delta',
  'tool_start',
  'tool_end',
  'message_complete',
  'run_complete',
  'run_error',
  'run_crashed',
  'permission_ask',
  'harness_event',
  'coordinator_plan_update',
  'session_title',
  'queue_update',
  'compaction',
];

export async function openStream(
  session_id: string,
  handlers: SSEHandlers = {},
): Promise<EventSource> {
  const { ticket } = await createSSETicket(session_id);
  const url = `${API_BASE}/sessions/${session_id}/stream?ticket=${encodeURIComponent(ticket)}`;
  const es = new EventSource(url);

  let retries = 0;
  const MAX_RETRIES = 5;
  const BASE_DELAY_MS = 1000;

  const dispatch = (type: SSEEventType) => (e: MessageEvent) => {
    retries = 0;
    if (!handlers.onEvent) return;
    try {
      const parsed = (e.data ? JSON.parse(e.data as string) : {}) as Record<string, unknown>;
      handlers.onEvent({ type, ...parsed });
    } catch {
      handlers.onEvent({ type, raw: e.data as string });
    }
  };

  for (const t of SSE_EVENT_TYPES) {
    es.addEventListener(t, dispatch(t) as EventListener);
  }

  es.onmessage = dispatch('message') as EventListener;

  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) {
      if (handlers.onClose) handlers.onClose();
      return;
    }
    if (retries < MAX_RETRIES) {
      retries++;
      const delay = BASE_DELAY_MS * Math.pow(2, retries - 1);
      console.warn(`[PrismAPI] SSE error, retry ${retries}/${MAX_RETRIES} in ${delay}ms`);
      setTimeout(() => {
        if (retries >= MAX_RETRIES && handlers.onError) {
          handlers.onError(new Error('SSE max retries exceeded'));
          es.close();
        }
      }, delay);
    } else {
      if (handlers.onError) handlers.onError(new Error('SSE connection failed'));
      es.close();
    }
  };

  return es;
}

// ---------------------------------------------------------------------------
// Sessions namespace
// ---------------------------------------------------------------------------

export const sessions = {
  list(query?: RequestOpts['query']): Promise<PagedResponse<SessionListItem>> {
    return request<PagedResponse<SessionListItem>>('GET', '/sessions', { query });
  },
  get(id: string): Promise<Session> {
    return request<Session>('GET', `/sessions/${id}`);
  },
  create(body: { title?: string; config_snapshot?: Record<string, unknown> }): Promise<Session> {
    return request<Session>('POST', '/sessions', { json: body });
  },
  update(id: string, body: {
    title?: string;
    is_pinned?: boolean;
    config_snapshot?: Record<string, unknown>;
  }): Promise<Session> {
    return request<Session>('PATCH', `/sessions/${id}`, { json: body });
  },
  delete(id: string): Promise<null> {
    return request<null>('DELETE', `/sessions/${id}`);
  },
  listMessages(id: string, query?: RequestOpts['query']): Promise<PagedResponse<Message>> {
    return request<PagedResponse<Message>>('GET', `/sessions/${id}/messages`, { query });
  },
  listRuns(id: string): Promise<RunListItem[]> {
    return request<RunListItem[]>('GET', `/sessions/${id}/runs`);
  },
  permissionAnswer(id: string, body: Record<string, unknown>): Promise<null> {
    return request<null>('POST', `/sessions/${id}/permission-answer`, { json: body });
  },
};

// ---------------------------------------------------------------------------
// Tasks namespace
// ---------------------------------------------------------------------------

export const tasks = {
  submit(body: {
    session_id?: string;
    prompt: string;
    agent_type?: string;
  }): Promise<SubmitTaskResponse> {
    return request<SubmitTaskResponse>('POST', '/tasks', { json: body });
  },
};

// ---------------------------------------------------------------------------
// Runs namespace
// ---------------------------------------------------------------------------

export const runs = {
  get(id: string): Promise<Run> {
    return request<Run>('GET', `/runs/${id}`);
  },
  cancel(id: string, body?: { mode?: 'graceful' | 'force' | 'also_cancel_queue' }): Promise<null> {
    return request<null>('POST', `/runs/${id}/cancel`, { json: body });
  },
  resume(id: string): Promise<null> {
    return request<null>('POST', `/runs/${id}/resume`);
  },
};

// ---------------------------------------------------------------------------
// Admin namespace
// ---------------------------------------------------------------------------

export const admin = {
  listUsers(params: { page?: number; search?: string } = {}): Promise<PagedResponse<AdminUser>> {
    return request<PagedResponse<AdminUser>>('GET', '/admin/users', {
      query: { page: params.page ?? 1, search: params.search },
    });
  },
  updateUser(userId: string, body: Record<string, unknown>): Promise<AdminUser> {
    return request<AdminUser>('PATCH', `/admin/users/${userId}`, { json: body });
  },
  changeUserRole(userId: string, role: 'admin' | 'user'): Promise<AdminUser> {
    return request<AdminUser>('PATCH', `/admin/users/${userId}/role`, { json: { role } });
  },
  disableUser(userId: string): Promise<null> {
    return request<null>('DELETE', `/admin/users/${userId}`);
  },
  listInviteCodes(): Promise<InviteCode[]> {
    return request<InviteCode[]>('GET', '/admin/invite-codes');
  },
  createInviteCode(params: {
    max_uses?: number;
    expires_at?: string;
  } = {}): Promise<InviteCode> {
    return request<InviteCode>('POST', '/admin/invite-codes', { json: params });
  },
  revokeInviteCode(inviteId: string): Promise<null> {
    return request<null>('DELETE', `/admin/invite-codes/${inviteId}`);
  },
  listAuditLogs(params: {
    action?: string;
    user_id?: string;
    start_date?: string;
    end_date?: string;
    limit?: number;
    page?: number;
  } = {}): Promise<PagedResponse<AuditLog>> {
    return request<PagedResponse<AuditLog>>('GET', '/admin/audit-logs', {
      query: {
        action: params.action,
        user_id: params.user_id,
        start_date: params.start_date,
        end_date: params.end_date,
        limit: params.limit ?? 100,
        page: params.page ?? 1,
      },
    });
  },
  exportAuditLogsCSV(params: {
    action?: string;
    user_id?: string;
    start_date?: string;
    end_date?: string;
  } = {}): Promise<Blob> {
    const q = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null) as [string, string][],
      ),
    );
    const path = '/admin/audit-logs/export' + (q.toString() ? '?' + q.toString() : '');
    return requestBlob('GET', path, {}, 'audit-logs.csv');
  },
  getDashboard(): Promise<SystemStats> {
    return request<SystemStats>('GET', '/admin/stats/dashboard');
  },
  getUsage(params: {
    group_by?: string;
    start_date?: string;
    end_date?: string;
  } = {}): Promise<unknown> {
    return request<unknown>('GET', '/admin/usage', {
      query: { group_by: params.group_by ?? 'day', start_date: params.start_date, end_date: params.end_date },
    });
  },
  getAlertConfig(): Promise<unknown> {
    return request<unknown>('GET', '/admin/alerts/config');
  },
  updateAlertConfig(body: Record<string, unknown>): Promise<unknown> {
    return request<unknown>('PATCH', '/admin/alerts/config', { json: body });
  },
};

// ---------------------------------------------------------------------------
// Providers namespace
// ---------------------------------------------------------------------------

export const providers = {
  list(): Promise<Provider[]> {
    return request<Provider[]>('GET', '/providers');
  },
  get(id: string): Promise<Provider> {
    return request<Provider>('GET', `/providers/${id}`);
  },
  create(body: {
    name: string;
    protocol: 'anthropic' | 'openai';
    base_url: string;
    api_key: string;
    model_id: string;
    is_default?: boolean;
    priority?: number;
    config?: Record<string, unknown>;
  }): Promise<Provider> {
    return request<Provider>('POST', '/providers', { json: body });
  },
  update(id: string, body: {
    name?: string;
    api_key?: string;
    is_default?: boolean;
    priority?: number;
    config?: Record<string, unknown>;
  }): Promise<Provider> {
    return request<Provider>('PUT', `/providers/${id}`, { json: body });
  },
  delete(id: string): Promise<null> {
    return request<null>('DELETE', `/providers/${id}`);
  },
  test(id: string): Promise<TestProviderResponse> {
    return request<TestProviderResponse>('POST', `/providers/${id}/test`);
  },
  usage(params: {
    group_by?: string;
    start_date?: string;
    end_date?: string;
  } = {}): Promise<unknown> {
    return request<unknown>('GET', '/providers/usage', {
      query: { group_by: params.group_by ?? 'day', start_date: params.start_date, end_date: params.end_date },
    });
  },
  presets(): Promise<ProviderPreset[]> {
    return request<ProviderPreset[]>('GET', '/providers/presets');
  },
};

// ---------------------------------------------------------------------------
// MCP namespace
// ---------------------------------------------------------------------------

export const mcp = {
  listServers(): Promise<McpServer[]> {
    return request<McpServer[]>('GET', '/mcp-servers');
  },
  getServer(id: string): Promise<McpServer> {
    return request<McpServer>('GET', `/mcp-servers/${id}`);
  },
  createServer(body: {
    name: string;
    description?: string;
    transport?: 'stdio' | 'http';
    command?: string;
    args?: string[];
    env?: Record<string, string>;
    url?: string;
    headers?: Record<string, string>;
  }): Promise<McpServer> {
    return request<McpServer>('POST', '/mcp-servers', { json: body });
  },
  deleteServer(id: string): Promise<null> {
    return request<null>('DELETE', `/mcp-servers/${id}`);
  },
  testServer(id: string): Promise<MCPTestResponse> {
    return request<MCPTestResponse>('POST', `/mcp-servers/${id}/test`);
  },
  listInstalls(): Promise<MCPInstall[]> {
    return request<MCPInstall[]>('GET', '/mcp-installs');
  },
  install(body: {
    mcp_server_id: string;
    config_override?: Record<string, unknown>;
  }): Promise<MCPInstall> {
    return request<MCPInstall>('POST', '/mcp-installs', { json: body });
  },
  updateInstall(id: string, body: {
    is_enabled?: boolean;
    config_override?: Record<string, unknown>;
  }): Promise<MCPInstall> {
    return request<MCPInstall>('PATCH', `/mcp-installs/${id}`, { json: body });
  },
  uninstall(id: string): Promise<null> {
    return request<null>('DELETE', `/mcp-installs/${id}`);
  },
};

// ---------------------------------------------------------------------------
// Skills namespace
// ---------------------------------------------------------------------------

export const skills = {
  search(params: { q?: string; source?: string; limit?: number } = {}): Promise<SkillPackage[]> {
    return request<SkillPackage[]>('GET', '/skills/search', {
      query: { q: params.q, source: params.source, limit: params.limit },
    });
  },
  listInstalled(): Promise<SkillInstall[]> {
    return request<SkillInstall[]>('GET', '/skills/installed');
  },
  get(name: string): Promise<SkillPackage> {
    return request<SkillPackage>('GET', `/skills/${name}`);
  },
  install(params: {
    skill_name?: string;
    source: 'local' | 'github' | 'marketplace';
    source_url?: string;
    version?: string;
    install_path?: string;
    content_base64?: string;
    has_hooks?: boolean;
    has_mcp?: boolean;
    marketplace_id?: string;
    plugin_name?: string;
  }): Promise<SkillInstall> {
    return request<SkillInstall>('POST', '/skills/install', { json: params });
  },
  patch(name: string, params: { enabled: boolean }): Promise<SkillInstall> {
    return request<SkillInstall>('PATCH', `/skills/${name}`, { json: params });
  },
  getContent(name: string): Promise<SkillContent> {
    return request<SkillContent>('GET', `/skills/${name}/content`);
  },
  getReadme(name: string, sourceUrl?: string): Promise<SkillReadme> {
    const params = sourceUrl ? `?source_url=${encodeURIComponent(sourceUrl)}` : '';
    return request<SkillReadme>('GET', `/skills/${encodeURIComponent(name)}/readme${params}`);
  },
  update(name: string): Promise<null> {
    return request<null>('POST', `/skills/${name}/update`);
  },
  uninstall(name: string): Promise<null> {
    return request<null>('DELETE', `/skills/${name}`);
  },
  installByUrl(url: string, name?: string): Promise<SkillInstall> {
    return request<SkillInstall>('POST', '/skills/install-url', { json: { url, name } });
  },
};

// ---------------------------------------------------------------------------
// Plugins namespace
// ---------------------------------------------------------------------------

export const plugins = {
  listLibrary(): Promise<PluginLibraryItem[]> {
    return request<PluginLibraryItem[]>('GET', '/plugins/library');
  },
  save(params: {
    name?: string;
    version?: string;
    description?: string;
    manifest_yaml?: string;
    manifest_json?: Record<string, unknown>;
    type?: string;
    permissions?: string[];
  }): Promise<PluginLibraryItem> {
    return request<PluginLibraryItem>('POST', '/plugins/save', { json: params });
  },
  patch(pluginId: string, params: { enabled: boolean }): Promise<PluginLibraryItem> {
    return request<PluginLibraryItem>('PATCH', `/plugins/library/${pluginId}`, { json: params });
  },
  delete(pluginId: string): Promise<null> {
    return request<null>('DELETE', `/plugins/library/${pluginId}`);
  },
};

// ---------------------------------------------------------------------------
// Marketplaces namespace
// ---------------------------------------------------------------------------

export const marketplaces = {
  presets(): Promise<Marketplace[]> {
    return request<Marketplace[]>('GET', '/marketplaces/presets');
  },
  list(): Promise<Marketplace[]> {
    return request<Marketplace[]>('GET', '/marketplaces');
  },
  create(params: { url: string; name: string }): Promise<Marketplace> {
    return request<Marketplace>('POST', '/marketplaces', { json: params });
  },
  sync(marketplaceId: string): Promise<Marketplace> {
    return request<Marketplace>('POST', `/marketplaces/${marketplaceId}/sync`);
  },
  delete(marketplaceId: string): Promise<null> {
    return request<null>('DELETE', `/marketplaces/${marketplaceId}`);
  },
  installPlugin(marketplaceId: string, pluginName: string): Promise<InstallReport> {
    return request<InstallReport>(
      'POST',
      `/marketplaces/${marketplaceId}/plugins/${encodeURIComponent(pluginName)}/install`,
    );
  },
};

// ---------------------------------------------------------------------------
// IM namespace
// ---------------------------------------------------------------------------

export const im = {
  listChannels(): Promise<IMChannel[]> {
    return request<IMChannel[]>('GET', '/im/channels');
  },
  updateChannel(channel: string, body: {
    is_enabled?: boolean;
    config?: Record<string, unknown>;
  }): Promise<IMChannel> {
    return request<IMChannel>('PATCH', `/im/channels/${channel}`, { json: body });
  },
  listBindings(): Promise<IMBinding[]> {
    return request<IMBinding[]>('GET', '/im/bindings');
  },
  generatePairingCode(params: { channel: string }): Promise<PairingCodeResponse> {
    return request<PairingCodeResponse>('POST', '/im/bindings/pair', {
      query: { channel: params.channel },
    });
  },
  unbind(bindingId: string): Promise<null> {
    return request<null>('DELETE', `/im/bindings/${bindingId}`);
  },
};

// ---------------------------------------------------------------------------
// Harness namespace
// ---------------------------------------------------------------------------

export const harness = {
  config(): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('GET', '/harness/config');
  },
  analytics(params: { days?: number; offset_days?: number } = {}): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('GET', '/harness/analytics', {
      query: { days: params.days ?? 7, offset_days: params.offset_days ?? 0 },
    });
  },
  entropyCheck(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('POST', '/harness/entropy-check', { json: body });
  },
  thresholdCalibrate(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('POST', '/harness/threshold-calibrate', { json: body });
  },
};

// ---------------------------------------------------------------------------
// Auth namespace (grouped alias for backwards compatibility with window.PrismAPI)
// ---------------------------------------------------------------------------

export const auth = {
  me,
  createSSETicket,
  providers: authProviders,
  emailMagicRequest,
  emailMagicVerify,
  emailOtpRequest,
  emailOtpVerify,
  forgotPassword,
  resetPassword,
  changePassword,
  phoneRegister,
  phoneLogin,
  googleComplete,
};

// ---------------------------------------------------------------------------
// Frontend error reporting (no-auth)
// ---------------------------------------------------------------------------

export async function reportError(params: ErrorReport): Promise<void> {
  try {
    const payload = {
      message: params.message ?? 'Unknown error',
      stack: params.stack ?? '',
      name: params.name ?? 'Error',
      url: params.url ?? window.location.href,
      user_agent: navigator.userAgent,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      user_id: currentUser()?.id ?? null,
      session_id: null,
      context: params.context ?? {},
      severity: params.severity ?? 'error',
      timestamp: new Date().toISOString(),
    };
    await fetch(API_BASE + '/frontend-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch { /* swallow — don't create an error loop */ }
}
