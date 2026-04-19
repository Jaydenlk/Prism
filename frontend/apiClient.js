/**
 * Prism v2 API Client — vanilla JS, no React dependency
 * Exported to window.PrismAPI
 *
 * Auth flow:
 *   - access_token stored in sessionStorage (cleared on tab close)
 *   - refresh_token is HttpOnly cookie managed by browser
 *   - 401 → auto-refresh → retry; still 401 → emit prism:unauthorized
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
      const data = await res.json();
      if (data.access_token) {
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
   * Returns parsed JSON body, or null for 204.
   * Throws on non-2xx (after refresh attempt).
   */
  async function request(method, path, opts = {}) {
    const res = await _fetchRaw(method, path, opts);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body && body.detail) {
          detail = typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail);
        }
      } catch { /* non-JSON error body */ }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    try { return await res.json(); } catch { return null; }
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

    // SSE
    openStream,

    // Domain helpers
    sessions,
    tasks,
    runs,

    auth: {
      me,
      createSSETicket,
    },

    // Error reporting
    reportError,
  };
})();
