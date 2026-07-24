import { withApiAuthHeaders } from '../auth/token'

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: withApiAuthHeaders(options.headers),
  })
  const payload = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(payload?.error || `Erreur HTTP ${response.status}`)
  }

  return payload
}

export async function fetchHelloAssoLatestItems(campaignId, options = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    return { items: [], importMeta: null }
  }

  const payload = await fetchJson(
    `/api/helloasso/items/latest/?campaignId=${encodeURIComponent(String(normalizedCampaignId))}`,
    options,
  )

  return {
    items: Array.isArray(payload?.items) ? payload.items : [],
    importMeta: payload?.import && typeof payload.import === 'object' ? payload.import : null,
  }
}

export async function importHelloAssoCampaign(campaignId, options = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    throw new Error('campaignId must be a number')
  }

  const params = new URLSearchParams({
    campaignId: String(normalizedCampaignId),
    withDetails: String(options.withDetails ?? true),
  })
  return fetchJson(`/api/helloasso/import/?${params.toString()}`, { signal: options.signal })
}
