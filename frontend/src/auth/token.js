const STORAGE_KEY = 'organization_admin_api_token'

function readEnvToken() {
  const raw = import.meta.env?.VITE_API_AUTH_TOKEN
  return typeof raw === 'string' ? raw.trim() : ''
}

export function getStoredToken() {
  if (typeof window === 'undefined') return readEnvToken()
  const local = String(window.localStorage.getItem(STORAGE_KEY) || '').trim()
  return local || readEnvToken()
}

export function setStoredToken(token) {
  const normalized = String(token || '').trim()
  if (typeof window !== 'undefined') {
    if (normalized) {
      window.localStorage.setItem(STORAGE_KEY, normalized)
    } else {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }
  syncTokenCookie(normalized)
}

export function clearStoredToken() {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(STORAGE_KEY)
  }
  syncTokenCookie('')
}

export function syncTokenCookie(token) {
  if (typeof document === 'undefined') return
  const normalized = String(token || '').trim()
  if (globalThis.cookieStore && typeof globalThis.cookieStore.set === 'function') {
    if (!normalized) {
      void globalThis.cookieStore.delete('api_token')
      return
    }
    void globalThis.cookieStore.set({
      name: 'api_token',
      value: normalized,
      path: '/',
      sameSite: 'lax',
    })
    return
  }

  if (!normalized) {
    // biome-ignore lint/suspicious/noDocumentCookie: Fallback for runtimes without Cookie Store API.
    document.cookie = 'api_token=; Path=/; Max-Age=0; SameSite=Lax'
    return
  }
  // biome-ignore lint/suspicious/noDocumentCookie: Fallback for runtimes without Cookie Store API.
  document.cookie = `api_token=${encodeURIComponent(normalized)}; Path=/; SameSite=Lax`
}

export function withApiAuthHeaders(headers = {}) {
  const normalized = { ...headers }
  const token = getStoredToken()
  if (token) {
    normalized.Authorization = `Bearer ${token}`
  }
  return normalized
}
