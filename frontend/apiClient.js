/**
 * Prism v2 API Client — vanilla JS, no React dependency
 * Exported to window.PrismAPI
 *
 * Auth flow:
 *   - access_token stored in sessionStorage (cleared on tab close)
 *   - refresh_token is HttpOnly cookie managed by browser
 *   - 401 → auto-refresh → retry; still 401 → emit prism:unauthorized
 *
 * Envelope: backend wraps all responses as { data: <payload>, error: null }
 *   request() unwraps to .data automatically.
 */
(function () {
  'use strict';

  const API_BASE = (window.PRISM_API_BASE || '/api/v1').replace(/\/$/, '');

  /* ── Token storage ────────────────────────────────────────────── */
  const TOKEN_KEY = 'prism_access_token';
  const USER_KEY  = 'prism_current_user';

  function _storeToken(token) {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  }

  function _storeUser(user) {
    if (user) sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    else sessionStorage.removeItem(USER_KEY);
  }

  function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  function isAuthenticated() {
    return !!getToken();
  }

  function currentUser() {
    const raw = sessionStorage.getItem(USER_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  }

  /* ── Base fetch wrapper ───────────────────────────────────────── */
  let _refreshing = null; // singleton promise to avoid refresh storms

  async function _fetchRaw(method, path, { json, query } = {}, skipRefresh = false) {
    let url = API_BASE + path;
    if (query) {
      const params = new URLSearchParams(
        Object.fromEntries(Object.entries(query).filter(([, v]) => v !== undefined && v !== null))
      );
      url += '?' + params.toString();
    }

    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;

    const init = {
      method: method.toUpperCase(),
      headers,
      credentials: 'include', // send refresh_token cookie
    };
    if (json !== undefined) init.body = JSON.stringify(json);

    const res = await fetch(url, init);

    // Auth endpoints must not trigger the refresh loop:
    // a wrong-password 401 on /auth/login must not fire _doRefresh() or prism:unauthorized.
    const _noRefreshPaths = ['/auth/login', '/auth/register', '/auth/refresh'];
    const isAuthPath = _noRefreshPaths.some(p => path === p || path.startsWith(p + '?'));

    if (res.status === 401 && !skipRefresh && !isAuthPath) {
      // Try refresh once
      if (!_refreshing) {
        _refreshing = _doRefresh().finally(() => { _refreshing = null; });
      }
      const ok = await _refreshing;
      if (ok) {
        // retry with new token
        return _fetchRaw(method, path, { json, query }, true);
      } else {
        _storeToken(null);
        _storeUser(null);
        window.dispatchEvent(new CustomEvent('prism:unauthorized'));
        throw Object.assign(new Error('Unauthorized'), { status: 401 });
      }
    }

    return res;
  }

  async function _doRefresh() {
    try {
      const res = await fetch(API_BASE + '/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) return false;
      const body = await res.json();
      // unwrap envelope { data: { access_token }, error }
      const data = body && body.data !== undefined ? body.data : body;
      if (data && data.access_token) {
        _storeToken(data.access_token);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  /**
   * General-purpose fetch wrapper.
   * Returns unwrapped payload (body.data when envelope present), or null for 204.
   * Throws on non-2xx (after refresh attempt).
   */
  async function request(method, path, opts = {}) {
    const res = await _fetchRaw(method, path, opts);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        // backend error shape: { detail: string } or envelope { data, error }
        if (body && body.detail) {
          detail = typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail);
        } else if (body && body.error) {
          detail = typeof body.error === 'string' ? body.error : JSON.stringify(body.error);
        }
      } catch { /* non-JSON error body */ }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    try {
      const body = await res.json();
      // Unwrap { data: <payload>, error: null } envelope automatically
      if (body && typeof body === 'object' && 'data' in body && 'error' in body) {
        return body.data;
      }
      return body;
    } catch { return null; }
  }

  /**
   * Like request() but returns a Blob (for CSV/file downloads).
   * Triggers browser download via hidden anchor.
   */
  async function requestBlob(method, path, opts = {}, filename = 'download') {
    const res = await _fetchRaw(method, path, opts);
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
    return blob;
  }

  /* ── Auth ─────────────────────────────────────────────────────── */
  async function login(email, password) {
    const data = await request('POST', '/auth/login', { json: { email, password } });
    _storeToken(data.access_token);
    // fetch user profile immediately
    const user = await me();
    return { user, access_token: data.access_token };
  }

  async function register({ email, username, password, invite_code }) {
    return request('POST', '/auth/register', { json: { email, username, password, invite_code } });
  }

  async function refresh() {
    const ok = await _doRefresh();
    return ok;
  }

  async function logout() {
    try {
      await request('POST', '/auth/logout');
    } catch { /* best-effort */ }
    _storeToken(null);
    _storeUser(null);
  }

  async function me() {
    const user = await request('GET', '/auth/me');
    _storeUser(user);
    return user;
  }

  async function createSSETicket(session_id) {
    return request('POST', '/auth/sse-ticket', { json: { session_id } });
  }

  /* ── Health ───────────────────────────────────────────────────── */
  async function healthDetailed() {
    // GET /health/detailed — admin only; note: NOT under /api/v1 path prefix
    // Actually it IS under /api/v1 per the manual
    return request('GET', '/health/detailed');
  }

  /* ── SSE helper ───────────────────────────────────────────────── */
  /**
   * Opens an authenticated SSE stream for a session.
   *
   * @param {string} session_id
   * @param {{ onEvent, onError, onClose }} handlers
   * @returns {Promise<EventSource>}  resolves once ticket acquired and ES opened
   */
  async function openStream(session_id, { onEvent, onError, onClose } = {}) {
    const { ticket } = await createSSETicket(session_id);
    const url = `${API_BASE}/sessions/${session_id}/stream?ticket=${encodeURIComponent(ticket)}`;
    const es = new EventSource(url);

    let retries = 0;
    const MAX_RETRIES = 5;
    const BASE_DELAY_MS = 1000;

    es.onmessage = (e) => {
      retries = 0; // reset on successful message
      if (onEvent) {
        try {
          const parsed = JSON.parse(e.data);
          onEvent(parsed);
        } catch {
          onEvent(e.data);
        }
      }
    };

    es.onerror = (e) => {
      if (es.readyState === EventSource.CLOSED) {
        if (onClose) onClose();
        return;
      }
      if (retries < MAX_RETRIES) {
        retries++;
        const delay = BASE_DELAY_MS * Math.pow(2, retries - 1); // 1s, 2s, 4s, 8s, 16s
        console.warn(`[PrismAPI] SSE error, retry ${retries}/${MAX_RETRIES} in ${delay}ms`);
        // EventSource auto-reconnects; we just track retries for the give-up threshold
        setTimeout(() => {
          if (retries >= MAX_RETRIES && onError) {
            onError(new Error('SSE max retries exceeded'));
            es.close();
          }
        }, delay);
      } else {
        if (onError) onError(new Error('SSE connection failed'));
        es.close();
      }
    };

    return es;
  }

  /* ── Sessions ─────────────────────────────────────────────────── */
  const sessions = {
    list(query) {
      return request('GET', '/sessions', { query });
    },
    get(id) {
      return request('GET', `/sessions/${id}`);
    },
    create(body) {
      return request('POST', '/sessions', { json: body });
    },
    update(id, body) {
      return request('PATCH', `/sessions/${id}`, { json: body });
    },
    delete(id) {
      return request('DELETE', `/sessions/${id}`);
    },
    listMessages(id, query) {
      return request('GET', `/sessions/${id}/messages`, { query });
    },
    listRuns(id) {
      return request('GET', `/sessions/${id}/runs`);
    },
    permissionAnswer(id, body) {
      return request('POST', `/sessions/${id}/permission-answer`, { json: body });
    },
  };

  /* ── Tasks ────────────────────────────────────────────────────── */
  const tasks = {
    submit(body) {
      // body: { session_id, prompt, agent_type? }
      return request('POST', '/tasks', { json: body });
    },
  };

  /* ── Runs ─────────────────────────────────────────────────────── */
  const runs = {
    get(id) {
      return request('GET', `/runs/${id}`);
    },
    cancel(id, body) {
      return request('POST', `/runs/${id}/cancel`, { json: body });
    },
    resume(id) {
      return request('POST', `/runs/${id}/resume`);
    },
  };

  /* ── Admin ────────────────────────────────────────────────────── */
  const admin = {
    // Users
    listUsers({ page = 1, search } = {}) {
      return request('GET', '/admin/users', { query: { page, search } });
    },
    updateUser(userId, body) {
      return request('PATCH', `/admin/users/${userId}`, { json: body });
    },
    changeUserRole(userId, role) {
      return request('PATCH', `/admin/users/${userId}/role`, { json: { role } });
    },
    disableUser(userId) {
      return request('DELETE', `/admin/users/${userId}`);
    },

    // Invite codes
    listInviteCodes() {
      return request('GET', '/admin/invite-codes');
    },
    createInviteCode({ max_uses, expires_at } = {}) {
      return request('POST', '/admin/invite-codes', { json: { max_uses, expires_at } });
    },
    revokeInviteCode(inviteId) {
      return request('DELETE', `/admin/invite-codes/${inviteId}`);
    },

    // Audit logs
    listAuditLogs({ action, user_id, start_date, end_date, limit = 100, page = 1 } = {}) {
      return request('GET', '/admin/audit-logs', {
        query: { action, user_id, start_date, end_date, limit, page },
      });
    },
    exportAuditLogsCSV({ action, user_id, start_date, end_date } = {}) {
      const q = new URLSearchParams(
        Object.fromEntries(
          Object.entries({ action, user_id, start_date, end_date })
            .filter(([, v]) => v !== undefined && v !== null)
        )
      );
      const path = '/admin/audit-logs/export' + (q.toString() ? '?' + q.toString() : '');
      return requestBlob('GET', path, {}, 'audit-logs.csv');
    },

    // Stats
    getDashboard() {
      return request('GET', '/admin/stats/dashboard');
    },
    getUsage({ group_by = 'day', start_date, end_date } = {}) {
      return request('GET', '/admin/usage', { query: { group_by, start_date, end_date } });
    },

    // Alert config
    getAlertConfig() {
      return request('GET', '/admin/alerts/config');
    },
    updateAlertConfig(body) {
      return request('PATCH', '/admin/alerts/config', { json: body });
    },
  };

  /* ── Providers ────────────────────────────────────────────────── */
  const providers = {
    list() {
      return request('GET', '/providers');
    },
    get(id) {
      return request('GET', `/providers/${id}`);
    },
    create(body) {
      return request('POST', '/providers', { json: body });
    },
    update(id, body) {
      return request('PUT', `/providers/${id}`, { json: body });
    },
    delete_(id) {
      return request('DELETE', `/providers/${id}`);
    },
    test(id) {
      return request('POST', `/providers/${id}/test`);
    },
    usage({ group_by = 'day', start_date, end_date } = {}) {
      return request('GET', '/providers/usage', { query: { group_by, start_date, end_date } });
    },
    presets() {
      return request('GET', '/providers/presets');
    },
  };

  /* ── MCP ──────────────────────────────────────────────────────── */
  const mcp = {
    listServers() {
      return request('GET', '/mcp-servers');
    },
    getServer(id) {
      return request('GET', `/mcp-servers/${id}`);
    },
    createServer(body) {
      return request('POST', '/mcp-servers', { json: body });
    },
    deleteServer(id) {
      return request('DELETE', `/mcp-servers/${id}`);
    },
    testServer(id) {
      return request('POST', `/mcp-servers/${id}/test`);
    },
    listInstalls() {
      return request('GET', '/mcp-installs');
    },
    install(body) {
      // body: { mcp_server_id }
      return request('POST', '/mcp-installs', { json: body });
    },
    updateInstall(id, body) {
      // body: { is_enabled?, config_override? }
      return request('PATCH', `/mcp-installs/${id}`, { json: body });
    },
    uninstall(id) {
      return request('DELETE', `/mcp-installs/${id}`);
    },
  };

  /* ── Skills ───────────────────────────────────────────────────── */
  const skills = {
    search({ q, source, limit } = {}) {
      return request('GET', '/skills/search', { query: { q, source, limit } });
    },
    listInstalled() {
      return request('GET', '/skills/installed');
    },
    get(name) {
      return request('GET', `/skills/${name}`);
    },
    install({ skill_name, source, source_url, version, install_path }) {
      return request('POST', '/skills/install', { json: { skill_name, source, source_url, version, install_path } });
    },
    update(name) {
      return request('POST', `/skills/${name}/update`);
    },
    uninstall(name) {
      return request('DELETE', `/skills/${name}`);
    },
  };

  /* ── IM ───────────────────────────────────────────────────────── */
  const im = {
    listChannels() {
      return request('GET', '/im/channels');
    },
    updateChannel(channel, body) {
      return request('PATCH', `/im/channels/${channel}`, { json: body });
    },
    listBindings() {
      return request('GET', '/im/bindings');
    },
    generatePairingCode({ channel }) {
      // Backend expects channel as query param, not body
      return request('POST', '/im/bindings/pair', { query: { channel } });
    },
    unbind(bindingId) {
      return request('DELETE', `/im/bindings/${bindingId}`);
    },
  };

  /* ── Harness ──────────────────────────────────────────────────── */
  const harness = {
    config() {
      return request('GET', '/harness/config');
    },
    analytics({ window: w = '7d' } = {}) {
      return request('GET', '/harness/analytics', { query: { window: w } });
    },
    entropyCheck(body) {
      return request('POST', '/harness/entropy-check', { json: body });
    },
    thresholdCalibrate(body) {
      return request('POST', '/harness/threshold-calibrate', { json: body });
    },
  };

  /* ── Frontend error reporting (no-auth) ───────────────────────── */
  async function reportError({ message, stack, name, url, context, severity = 'error' }) {
    try {
      const payload = {
        message: message || 'Unknown error',
        stack: stack || '',
        name: name || 'Error',
        url: url || window.location.href,
        user_agent: navigator.userAgent,
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        user_id: currentUser()?.id || null,
        session_id: null,
        context: context || {},
        severity,
        timestamp: new Date().toISOString(),
      };
      await fetch(API_BASE + '/frontend-errors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch { /* swallow — don't create an error loop */ }
  }

  /* ── Export ───────────────────────────────────────────────────── */
  window.PrismAPI = {
    // State
    getToken,
    isAuthenticated,
    currentUser,

    // Auth
    login,
    register,
    refresh,
    logout,
    me,

    // Core request
    request,
    requestBlob,

    // SSE
    openStream,

    // Health
    healthDetailed,

    // Domain helpers
    sessions,
    tasks,
    runs,
    admin,
    providers,
    mcp,
    skills,
    im,
    harness,

    auth: {
      me,
      createSSETicket,
    },

    // Error reporting
    reportError,
  };
})();
