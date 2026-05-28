const BASE = '/api';

/** Read a cookie value by name */
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };

  // Attach CSRF token for any state-mutating request
  const method = (opts.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrf = getCookie('csrftoken');
    if (csrf) headers['X-CSRFToken'] = csrf;
  }

  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers,
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  // Auth
  csrf: ()              => fetch('/api/auth/csrf/', { credentials: 'include' }),
  login: (u, p)        => req('/auth/login/', { method: 'POST', body: JSON.stringify({ username: u, password: p }) }),
  logout: ()           => req('/auth/logout/', { method: 'POST' }),
  me: ()               => req('/auth/me/'),

  // Dashboard
  dashboard: ()        => req('/dashboard/'),

  // Batches
  batches: ()          => req('/batches/'),
  batch: (id)          => req(`/batches/${id}/`),
  lockBatch: (id)      => req(`/batches/${id}/lock/`, { method: 'POST' }),

  // Ingest
  ingest: (file, type) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('source_type', type);
    const csrf = getCookie('csrftoken');
    return fetch(`${BASE}/ingest/`, {
      method: 'POST',
      credentials: 'include',
      headers: csrf ? { 'X-CSRFToken': csrf } : {},
      body: fd,
    }).then(async r => { if (!r.ok) throw new Error(await r.text()); return r.json(); });
  },

  // Records
  records: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return req(`/records/${qs ? '?' + qs : ''}`);
  },
  record: (id)          => req(`/records/${id}/`),
  patchRecord: (id, data) => req(`/records/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  approve: (id)         => req(`/records/${id}/approve/`, { method: 'POST' }),
  flag: (id, reason)    => req(`/records/${id}/flag/`, { method: 'POST', body: JSON.stringify({ reason }) }),
  reject: (id, reason)  => req(`/records/${id}/reject/`, { method: 'POST', body: JSON.stringify({ reason }) }),
};
