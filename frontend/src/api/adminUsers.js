import { withApiAuthHeaders } from '../auth/token'

function csrfHeaders(headers) {
  const csrfToken = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith('csrftoken='))
    ?.slice('csrftoken='.length)
  return csrfToken ? { ...headers, 'X-CSRFToken': decodeURIComponent(csrfToken) } : headers
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: csrfHeaders(withApiAuthHeaders({ 'Content-Type': 'application/json', ...options.headers })),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(typeof payload?.error === 'string' ? payload.error : `HTTP ${response.status}`)
  }
  return payload
}

export async function fetchAdminUsers(query = '') {
  const params = new URLSearchParams()
  if (query.trim()) params.set('q', query.trim())
  const payload = await request(`/api/admin/users/${params.size ? `?${params}` : ''}`)
  return Array.isArray(payload?.users) ? payload.users : []
}

export async function createAdminUser(user) {
  const payload = await request('/api/admin/users/', {
    method: 'POST',
    body: JSON.stringify(user),
  })
  return payload?.user || null
}

export async function sendPasswordSetupLink(userId) {
  const payload = await request(`/api/admin/users/${userId}/password-setup/`, {
    method: 'POST',
    body: '{}',
  })
  return payload?.user || null
}

export async function sendPasswordResetLink(userId) {
  const payload = await request(`/api/admin/users/${userId}/password-reset/`, {
    method: 'POST',
    body: '{}',
  })
  return payload?.user || null
}
