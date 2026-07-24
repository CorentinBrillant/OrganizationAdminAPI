import { withApiAuthHeaders } from '../auth/token'

export async function fetchCampaigns() {
  const response = await fetch('/api/campaigns/', {
    headers: withApiAuthHeaders(),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const payload = await response.json()
  const campaigns = Array.isArray(payload?.campaigns) ? payload.campaigns : []

  return campaigns
    .map((campaign) => {
      const id = Number(campaign?.id)
      const title = String(campaign?.title || '').trim()
      if (!Number.isFinite(id) || !title) return null

      const rawLastMerge = campaign?.last_merge
      const last_merge = typeof rawLastMerge === 'string' && rawLastMerge.trim() ? rawLastMerge : null
      const rawLastManualEdition = campaign?.last_manual_edition
      const last_manual_edition =
        typeof rawLastManualEdition === 'string' && rawLastManualEdition.trim()
          ? rawLastManualEdition
          : null
      const helloasso_form_slug =
        typeof campaign?.helloasso_form_slug === 'string' ? campaign.helloasso_form_slug.trim() : ''

      return { id, title, last_merge, last_manual_edition, helloasso_form_slug }
    })
    .filter(Boolean)
}

export async function createCampaign({ title, status = 'active', helloasso_api_key = '', helloasso_form_slug = '' }) {
  const normalizedTitle = String(title || '').trim()
  if (!normalizedTitle) {
    throw new Error('title is required')
  }

  const csrfToken = readCookie('csrftoken')
  const headers = withApiAuthHeaders({ 'Content-Type': 'application/json' })
  if (csrfToken) headers['X-CSRFToken'] = csrfToken

  const response = await fetch('/api/campaigns/', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      title: normalizedTitle,
      status: String(status || '').trim() || 'active',
      helloasso_api_key: String(helloasso_api_key || '').trim(),
      helloasso_form_slug: String(helloasso_form_slug || '').trim(),
    }),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const payload = await response.json()
  const campaign = payload?.campaign || {}

  return {
    id: Number(campaign?.id),
    title: String(campaign?.title || '').trim(),
    last_merge:
      typeof campaign?.last_merge === 'string' && campaign.last_merge.trim() ? campaign.last_merge : null,
    last_manual_edition:
      typeof campaign?.last_manual_edition === 'string' && campaign.last_manual_edition.trim()
        ? campaign.last_manual_edition
        : null,
  }
}

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

export async function fetchCampaignMembers(campaignId, options = {}) {
  if (!Number.isFinite(Number(campaignId))) {
    return []
  }

  const response = await fetch(`/api/campaigns/${campaignId}/members/`, {
    headers: withApiAuthHeaders(),
    signal: options.signal,
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const payload = await response.json()
  const members = Array.isArray(payload?.members) ? payload.members : []

  return members.map((member) => ({
    id: Number(member?.id),
    first_name: String(member?.first_name || '').trim(),
    name: String(member?.name || '').trim(),
    ffck_licence: String(member?.ffck_licence || '').trim(),
    ffck_licence_type: String(member?.ffck_licence_type || '').trim(),
    ffck_certificat_expiration: String(member?.ffck_certificat_expiration || '').trim(),
    helloasso_form_slug: String(member?.helloasso_form_slug || '').trim(),
    email: String(member?.email || '').trim(),
    certificat: String(member?.certificat || '').trim(),
    certificat_file: {
      uploaded: Boolean(member?.certificat_file?.uploaded),
      filename: String(member?.certificat_file?.filename || '').trim(),
      content_type: String(member?.certificat_file?.content_type || '').trim(),
      size: Number(member?.certificat_file?.size) || 0,
      uploaded_at:
        typeof member?.certificat_file?.uploaded_at === 'string' &&
        member.certificat_file.uploaded_at.trim()
          ? member.certificat_file.uploaded_at
          : null,
    },
    autorisation_parentale: String(member?.autorisation_parentale || '').trim(),
    photo: String(member?.photo || '').trim(),
    option_ia: Boolean(member?.option_ia),
    manual_review: Boolean(member?.manual_review),
    badge_owned: Boolean(member?.badge_owned),
    badge_ordered: Boolean(member?.badge_ordered),
    campaign_id: Number(member?.campaign_id),
  }))
}

export async function fetchCampaignFfckLatestRows(campaignId, options = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    return { rows: [], exportMeta: null }
  }

  const response = await fetch(`/api/ffck/rows/latest/?campaignId=${encodeURIComponent(String(normalizedCampaignId))}`, {
    headers: withApiAuthHeaders(),
    signal: options.signal,
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const payload = await response.json()
  const rows = Array.isArray(payload?.rows) ? payload.rows : []
  const exportMeta = payload?.export && typeof payload.export === 'object' ? payload.export : null

  return {
    rows: rows.map((row) => ({
      id: Number(row?.id),
      row_index: Number(row?.row_index),
      licence: String(row?.licence || '').trim(),
      nom: String(row?.nom || '').trim(),
      categorie: String(row?.categorie || '').trim(),
      certificat: String(row?.certificat || '').trim(),
      member_id: Number(row?.member_id) || null,
      raw_row: row?.raw_row && typeof row.raw_row === 'object' ? row.raw_row : {},
    })),
    exportMeta,
  }
}

export async function importCampaignFfckExport(campaignId, options = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    throw new Error('campaignId must be a number')
  }

  const response = await fetch(
    `/api/federation/extract-excel/?campaignId=${encodeURIComponent(String(normalizedCampaignId))}`,
    {
      headers: withApiAuthHeaders(),
      signal: options.signal,
    },
  )
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload?.error || `Erreur HTTP ${response.status}`)
  }

  // Consume the download body so browser connections can be released before refreshing the imported rows.
  await response.arrayBuffer()
  const contentDisposition = response.headers.get('Content-Disposition')
  const utf8Filename = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const filename = utf8Filename
    ? decodeURIComponent(utf8Filename)
    : contentDisposition?.match(/filename="?([^";]+)"?/i)?.[1] || 'export.xlsx'
  const rowsCount = Number(response.headers.get('X-FFCK-Rows-Count'))

  return {
    filename,
    rowsCount: Number.isFinite(rowsCount) ? rowsCount : null,
  }
}

export async function saveCampaignManualEdition(campaignId, members) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    throw new Error('campaignId must be a number')
  }

  const payload = {
    members: Array.isArray(members) ? members : [],
  }

  const csrfToken = readCookie('csrftoken')
  const headers = withApiAuthHeaders({ 'Content-Type': 'application/json' })
  if (csrfToken) headers['X-CSRFToken'] = csrfToken

  const response = await fetch(`/api/campaigns/${normalizedCampaignId}/manual-edition/`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const body = await response.json()
  return {
    campaign_id: Number(body?.campaign_id),
    updated_member_ids: Array.isArray(body?.updated_member_ids) ? body.updated_member_ids : [],
    updated_count: Number(body?.updated_count) || 0,
    last_manual_edition:
      typeof body?.last_manual_edition === 'string' && body.last_manual_edition.trim()
        ? body.last_manual_edition
        : null,
  }
}

export async function updateCampaignSettings(campaignId, { helloasso_form_slug = '' } = {}) {
  const normalizedCampaignId = Number(campaignId)
  if (!Number.isFinite(normalizedCampaignId)) {
    throw new Error('campaignId must be a number')
  }

  const csrfToken = readCookie('csrftoken')
  const headers = withApiAuthHeaders({ 'Content-Type': 'application/json' })
  if (csrfToken) headers['X-CSRFToken'] = csrfToken

  const response = await fetch(`/api/campaigns/${normalizedCampaignId}/settings/`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      helloasso_form_slug: String(helloasso_form_slug || '').trim(),
    }),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const payload = await response.json()
  const campaign = payload?.campaign || {}
  return {
    id: Number(campaign?.id),
    title: String(campaign?.title || '').trim(),
    helloasso_form_slug: String(campaign?.helloasso_form_slug || '').trim(),
  }
}

export async function fetchHelloAssoMembershipForms() {
  const response = await fetch('/api/helloasso/membership-forms/', {
    headers: withApiAuthHeaders(),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || `HTTP ${response.status}`)
  }

  const forms = Array.isArray(payload?.forms) ? payload.forms : []
  return forms
    .map((form) => {
      const form_slug = String(form?.form_slug || '').trim()
      if (!form_slug) return null
      return {
        form_slug,
        title: String(form?.title || '').trim(),
        form_type: String(form?.form_type || '').trim(),
        state: String(form?.state || '').trim(),
      }
    })
    .filter(Boolean)
}
