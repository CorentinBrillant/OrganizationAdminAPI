import { withApiAuthHeaders } from '../auth/token'

function readCookie(name) {
  const cookieName = String(name || '').trim()
  if (!cookieName) return ''
  const parts = document.cookie ? document.cookie.split(';') : []
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith(`${cookieName}=`)) {
      return decodeURIComponent(trimmed.slice(cookieName.length + 1))
    }
  }
  return ''
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || `Erreur HTTP ${response.status}`)
  }
  return payload
}

export async function fetchBadgeLatestRows(campaignId, options = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    return { rows: [], importMeta: null }
  }

  const response = await fetch(`/api/badges/rows/latest/?campaignId=${encodeURIComponent(String(normalizedCampaignId))}`, {
    headers: withApiAuthHeaders(),
    signal: options.signal,
  })
  const payload = await readJson(response)
  return {
    rows: Array.isArray(payload?.rows) ? payload.rows : [],
    importMeta: payload?.import && typeof payload.import === 'object' ? payload.import : null,
  }
}

export async function importBadgeFile(campaignId, file, options = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    throw new Error('campaignId must be a number')
  }
  if (!(file instanceof File)) {
    throw new Error('file is required')
  }

  const formData = new FormData()
  formData.append('file', file)
  const csrfToken = readCookie('csrftoken')
  const headers = withApiAuthHeaders(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
  const response = await fetch(`/api/badges/import/?campaignId=${encodeURIComponent(String(normalizedCampaignId))}`, {
    method: 'POST',
    headers,
    body: formData,
    signal: options.signal,
  })
  return readJson(response)
}
