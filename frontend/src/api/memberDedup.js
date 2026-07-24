import { withApiAuthHeaders } from '../auth/token'

function readCookie(name) {
  const cookieName = String(name || '').trim()
  if (!cookieName) return ''
  const parts = document.cookie ? document.cookie.split(';') : []
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith(`${cookieName}=`)) return decodeURIComponent(trimmed.slice(cookieName.length + 1))
  }
  return ''
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.error || `Erreur HTTP ${response.status}`)
  return payload
}

export async function fetchMemberDuplicateSuggestions(campaignId, minScore, { refresh = false, signal } = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) return { suggestions: [], generation: null }

  const score = Number(minScore)
  const normalizedScore = Number.isFinite(score) ? Math.max(0, Math.min(1, score)) : 0.8
  const query = new URLSearchParams({
    campaignId: String(normalizedCampaignId),
    minScore: String(normalizedScore),
    refresh: refresh ? '1' : '0',
  })
  const response = await fetch(`/api/campaigns/member-duplicates/?${query}`, {
    headers: withApiAuthHeaders(),
    signal,
  })
  const payload = await readJson(response)
  return {
    suggestions: Array.isArray(payload?.suggestions) ? payload.suggestions : [],
    generation: payload?.generation && typeof payload.generation === 'object' ? payload.generation : null,
  }
}

export async function mergeMemberDuplicateSuggestion(campaignId, suggestionId, keepMemberId, { signal } = {}) {
  const normalizedCampaignId = Number(campaignId)
  const normalizedSuggestionId = Number(suggestionId)
  if (!Number.isFinite(normalizedCampaignId) || !Number.isFinite(normalizedSuggestionId)) {
    throw new Error('campaignId and suggestionId must be numbers')
  }

  const body = { suggestion_id: normalizedSuggestionId }
  const normalizedKeepMemberId = Number(keepMemberId)
  if (Number.isFinite(normalizedKeepMemberId)) body.keep_member_id = normalizedKeepMemberId

  const csrfToken = readCookie('csrftoken')
  const headers = withApiAuthHeaders({ 'Content-Type': 'application/json' })
  if (csrfToken) headers['X-CSRFToken'] = csrfToken
  const response = await fetch(`/api/campaigns/member-duplicates/merge/?campaignId=${encodeURIComponent(String(normalizedCampaignId))}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })
  return readJson(response)
}
