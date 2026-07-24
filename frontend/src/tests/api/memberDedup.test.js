import { beforeEach, describe, expect, it, vi } from 'vitest'

const { withApiAuthHeadersMock } = vi.hoisted(() => ({
  withApiAuthHeadersMock: vi.fn((headers = {}) => ({ Authorization: 'Bearer test-token', ...headers })),
}))

vi.mock('../../auth/token', () => ({ withApiAuthHeaders: withApiAuthHeadersMock }))

import { fetchMemberDuplicateSuggestions, mergeMemberDuplicateSuggestion } from '../../api/memberDedup'

describe('member dedup api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    globalThis.fetch = vi.fn()
    // biome-ignore lint/suspicious/noDocumentCookie: jsdom cookie fixture for CSRF coverage.
    document.cookie = 'csrftoken=test-csrf'
  })

  it('charge les suggestions avec le filtre et l’authentification', async () => {
    globalThis.fetch.mockResolvedValue({ ok: true, json: async () => ({ suggestions: [{ id: 1 }], generation: { suggestions_count: 1 } }) })

    await expect(fetchMemberDuplicateSuggestions(12, 0.8, { refresh: true })).resolves.toEqual({
      suggestions: [{ id: 1 }],
      generation: { suggestions_count: 1 },
    })
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/campaigns/member-duplicates/?campaignId=12&minScore=0.8&refresh=1', {
      headers: { Authorization: 'Bearer test-token' },
      signal: undefined,
    })
  })

  it('fusionne une suggestion avec CSRF et propage l’erreur backend', async () => {
    globalThis.fetch.mockResolvedValue({ ok: false, status: 400, json: async () => ({ error: 'Fusion impossible' }) })

    await expect(mergeMemberDuplicateSuggestion(12, 4, 8)).rejects.toThrow('Fusion impossible')
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/campaigns/member-duplicates/merge/?campaignId=12', {
      method: 'POST',
      headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json', 'X-CSRFToken': 'test-csrf' },
      body: JSON.stringify({ suggestion_id: 4, keep_member_id: 8 }),
      signal: undefined,
    })
  })
})
