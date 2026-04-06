const BASE = '/';

function getToken() {
  return localStorage.getItem('ats_token');
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.json) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.json);
  }

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem('ats_token');
    localStorage.removeItem('ats_user');
    window.location.href = '/login';
    return;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const errorMsg = data.detail || `HTTP ${res.status}: ${res.statusText}`;
    console.error(`API Error [${path}]:`, { status: res.status, error: errorMsg, data });
    throw new Error(errorMsg);
  }
  return data;
}

export const api = {
  // Auth
  signup: (body) => request('/auth/signup', { method: 'POST', json: body }),
  login:  (body) => request('/auth/login',  { method: 'POST', json: body }),
  me:     ()     => request('/auth/me'),

  // Analysis
  analyze: (formData) => request('/analyze', {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type — browser sets it with boundary for multipart
  }),
  history: () => request('/analyze/history'),
  listJobTemplates: () => request('/analyze/job-templates'),  // Public endpoint for users

  // Admin - Submissions
  adminSubmissions: () => request('/admin/submissions'),
  updateStatus: (id, status) => request(`/admin/submissions/${id}/status`, {
    method: 'PUT', json: { status }
  }),
  downloadResume: (id) => `/admin/resume/${id}`,

  // Admin - Job Templates
  createJobTemplate: (formData) => request('/admin/job-template', {
    method: 'POST',
    body: formData,
  }),
  listJobTemplatesAdmin: () => request('/admin/job-templates'),  // Admin endpoint for management
  getJobTemplate: (id) => request(`/admin/job-templates/${id}`),
  deleteJobTemplate: (id) => request(`/admin/job-templates/${id}`, {
    method: 'DELETE',
  }),
};