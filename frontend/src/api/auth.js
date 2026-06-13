import { withApiAuthHeaders } from '../auth/token'

export async function loginWithPassword({ username, password }) {
  const response = await fetch('/api/auth/login/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = typeof payload?.error === 'string' ? payload.error : `HTTP ${response.status}`
    throw new Error(message)
  }

  return {
    token: String(payload?.token || '').trim(),
    expiresIn: Number(payload?.expires_in) || 0,
    user: payload?.user && typeof payload.user === 'object' ? payload.user : null,
  }
}

export async function checkSession() {
  const response = await fetch('/api/auth/session/', {
    headers: withApiAuthHeaders(),
  })

  if (response.status === 401) {
    return { authenticated: false }
  }

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  return {
    authenticated: Boolean(payload?.authenticated),
    user: payload?.user && typeof payload.user === 'object' ? payload.user : null,
  }
}

export async function logoutSession() {
  const response = await fetch('/api/auth/logout/', {
    method: 'POST',
    headers: withApiAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({}),
  })

  if (response.status === 401) {
    return { loggedOut: true }
  }

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = typeof payload?.error === 'string' ? payload.error : `HTTP ${response.status}`
    throw new Error(message)
  }

  return { loggedOut: Boolean(payload?.logged_out) }
}
