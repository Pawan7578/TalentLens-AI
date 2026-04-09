// ─────────────────────────────────────────────────────────────────────────────
// api.js — TalentLens AI HTTP client
//
// URL strategy:
//   - Use VITE_API_URL when provided (local or production)
//   - Fall back to relative URLs when VITE_API_URL is not set
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');

console.log('🔌 API Base:', API_BASE || '(relative)', '| DEV:', import.meta.env.DEV);

function getToken() {
  return localStorage.getItem('ats_token');
}

function getRefreshToken() {
  return localStorage.getItem('ats_refresh_token');
}

function setAccessToken(token) {
  if (token) {
    localStorage.setItem('ats_token', token);
  }
}

function setRefreshToken(token) {
  if (token) {
    localStorage.setItem('ats_refresh_token', token);
  }
}

function clearAuth() {
  localStorage.removeItem('ats_token');
  localStorage.removeItem('ats_refresh_token');
  localStorage.removeItem('ats_user');
}

let refreshPromise = null;
const AUTH_ENDPOINTS = new Set(['/auth/login', '/auth/signup', '/auth/register', '/auth/refresh']);

/**
 * Build a URL for fetch() calls.
 * Uses VITE_API_URL when set; otherwise keeps relative paths.
 */
function buildUrl(path) {
  return API_BASE ? `${API_BASE}${path}` : path;
}

/**
 * Always returns a fully-qualified URL regardless of environment.
 * Use this for href / window.open / download links — NOT for fetch().
 */
function buildAbsoluteUrl(path) {
  if (API_BASE) {
    return `${API_BASE}${path}`;
  }

  if (typeof window !== 'undefined') {
    return new URL(path, window.location.origin).toString();
  }

  return path;
}

async function refreshAccessToken() {
  if (refreshPromise) {
    return refreshPromise;
  }

  const storedRefreshToken = getRefreshToken();
  if (!storedRefreshToken) {
    throw new Error('Session expired. Please sign in again.');
  }

  refreshPromise = (async () => {
    const res = await fetch(buildUrl('/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: storedRefreshToken }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data.detail || 'Session expired. Please sign in again.';
      throw new Error(message);
    }

    const nextAccessToken = data.access_token || data.token;
    const nextRefreshToken = data.refresh_token || storedRefreshToken;

    if (!nextAccessToken) {
      throw new Error('Token refresh failed: missing access token');
    }

    setAccessToken(nextAccessToken);
    setRefreshToken(nextRefreshToken);
    return nextAccessToken;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

async function request(path, options = {}) {
  const url = buildUrl(path);
  const baseOptions = { ...options };
  const baseHeaders = { ...(baseOptions.headers || {}) };

  if (Object.prototype.hasOwnProperty.call(baseOptions, 'json')) {
    baseHeaders['Content-Type'] = 'application/json';
    baseOptions.body = JSON.stringify(baseOptions.json);
    delete baseOptions.json;
  }
  delete baseOptions.headers;

  const makeRequest = (token) => {
    const headers = { ...baseHeaders };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return fetch(url, { ...baseOptions, headers });
  };

  const method = String(baseOptions.method || 'GET').toUpperCase();
  const maxNetworkAttempts = ['GET', 'HEAD', 'OPTIONS'].includes(method) ? 2 : 1;

  const makeRequestWithRetry = async (token) => {
    let attempt = 0;

    while (attempt < maxNetworkAttempts) {
      try {
        return await makeRequest(token);
      } catch (error) {
        attempt += 1;
        const shouldRetry = error instanceof TypeError && attempt < maxNetworkAttempts;

        if (!shouldRetry) {
          throw error;
        }

        console.warn(`Network retry ${attempt}/${maxNetworkAttempts - 1} for ${path}`);
        await new Promise(resolve => setTimeout(resolve, 300 * attempt));
      }
    }

    throw new TypeError(`Network request failed for ${path}`);
  };

  try {
    let token = getToken();
    let res = await makeRequestWithRetry(token);

    if (res.status === 401 && token && !AUTH_ENDPOINTS.has(path)) {
      try {
        token = await refreshAccessToken();
        res = await makeRequestWithRetry(token);
      } catch (refreshError) {
        clearAuth();
        throw refreshError;
      }
    }

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (res.status === 401 && !AUTH_ENDPOINTS.has(path)) {
        clearAuth();
      }

      const errorMsg = data.detail || `HTTP ${res.status}: ${res.statusText}`;
      console.error(`API Error [${path}]:`, { status: res.status, error: errorMsg, data });
      throw new Error(errorMsg);
    }

    return data;
  } catch (error) {
    if (error instanceof TypeError) {
      const configuredTarget = API_BASE || 'relative URL (set VITE_API_URL or configure a dev proxy target)';
      console.error(`Network Error [${path}]:`, error.message, '| API target:', configuredTarget);
    }
    throw error;
  }
}

export const api = {
  // ── Auth ────────────────────────────────────────────────────────────────────
  signup: (body) => request('/auth/signup', { method: 'POST', json: body }),
  login:  (body) => request('/auth/login',  { method: 'POST', json: body }),
  me:     ()     => request('/auth/me'),

  // ── Analysis ─────────────────────────────────────────────────────────────────
  analyze: (formData) =>
    request('/analyze', {
      method: 'POST',
      body: formData,
      // Do NOT set Content-Type here — browser sets it with the multipart boundary
    }),
  history:          ()   => request('/analyze/history'),
  listJobTemplates: ()   => request('/analyze/job-templates'),

  // ── Admin — Submissions ──────────────────────────────────────────────────────
  adminSubmissions: ()             => request('/admin/submissions'),
  updateStatus:     (id, status)   => request(`/admin/submissions/${id}/status`, {
    method: 'PUT',
    json: { status },
  }),
  bulkEmail:        (body)         => request('/admin/bulk-email', {
    method: 'POST',
    json: body,
  }),

  // Resume download — must be an absolute URL (used as an <a href> / window.open)
  // BUG FIX: was buildUrl() which returns a relative path in dev → broken download
  downloadResume: (id) => buildAbsoluteUrl(`/admin/resume/${id}`),

  // ── Admin — Job Templates ─────────────────────────────────────────────────────
  createJobTemplate: (formData) =>
    request('/admin/job-template', { method: 'POST', body: formData }),
  listJobTemplatesAdmin: ()    => request('/admin/job-templates'),
  getJobTemplate:        (id)  => request(`/admin/job-templates/${id}`),
  deleteJobTemplate:     (id)  => request(`/admin/job-templates/${id}`, { method: 'DELETE' }),
};
