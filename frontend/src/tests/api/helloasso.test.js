import { beforeEach, describe, expect, it, vi } from 'vitest'

const { withApiAuthHeadersMock } = vi.hoisted(() => ({
  withApiAuthHeadersMock: vi.fn((headers = {}) => ({ Authorization: 'Bearer test-token', ...headers })),
}))

vi.mock('../../auth/token', () => ({
  withApiAuthHeaders: withApiAuthHeadersMock,
}))

import { fetchHelloAssoLatestItems, importHelloAssoCampaign } from '../../api/helloasso'

describe('helloasso api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('charge la dernière importation avec les en-têtes d’authentification', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ items: [{ id: 1 }], import: { id: 4 } }) })

    await expect(fetchHelloAssoLatestItems(12)).resolves.toEqual({ items: [{ id: 1 }], importMeta: { id: 4 } })
    expect(global.fetch).toHaveBeenCalledWith('/api/helloasso/items/latest/?campaignId=12', {
      headers: { Authorization: 'Bearer test-token' },
    })
  })

  it('propage le message d’erreur du backend pendant une synchronisation', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 400, json: async () => ({ error: 'Formulaire absent' }) })

    await expect(importHelloAssoCampaign(12)).rejects.toThrow('Formulaire absent')
    expect(global.fetch).toHaveBeenCalledWith('/api/helloasso/import/?campaignId=12&withDetails=true', {
      signal: undefined,
      headers: { Authorization: 'Bearer test-token' },
    })
  })
})
