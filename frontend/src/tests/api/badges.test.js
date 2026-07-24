import { beforeEach, describe, expect, it, vi } from 'vitest'

const { withApiAuthHeadersMock } = vi.hoisted(() => ({
  withApiAuthHeadersMock: vi.fn((headers = {}) => ({ Authorization: 'Bearer test-token', ...headers })),
}))

vi.mock('../../auth/token', () => ({
  withApiAuthHeaders: withApiAuthHeadersMock,
}))

import { fetchBadgeLatestRows, importBadgeFile } from '../../api/badges'

describe('badges api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('charge le dernier import badges avec authentification', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ rows: [{ id: 1 }], import: { id: 3 } }) })

    await expect(fetchBadgeLatestRows(12)).resolves.toEqual({ rows: [{ id: 1 }], importMeta: { id: 3 } })
    expect(global.fetch).toHaveBeenCalledWith('/api/badges/rows/latest/?campaignId=12', {
      headers: { Authorization: 'Bearer test-token' },
      signal: undefined,
    })
  })

  it('importe le fichier et propage les erreurs backend', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 400, json: async () => ({ error: 'Fichier invalide' }) })

    await expect(importBadgeFile(12, new File(['badges'], 'badges.xlsx'))).rejects.toThrow('Fichier invalide')
  })
})
