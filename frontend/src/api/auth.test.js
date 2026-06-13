import { beforeEach, describe, expect, it, vi } from 'vitest'

const { withApiAuthHeadersMock } = vi.hoisted(() => ({
  withApiAuthHeadersMock: vi.fn((headers = {}) => ({
    Authorization: 'Bearer test-token',
    ...headers,
  })),
}))

vi.mock('../auth/token', () => ({
  withApiAuthHeaders: withApiAuthHeadersMock,
}))

import { checkSession, loginWithPassword, logoutSession } from './auth'

describe('auth api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('retourne une erreur backend explicite sur login échoué', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: 'Identifiants invalides' }),
    })

    await expect(loginWithPassword({ username: 'john', password: 'wrong' })).rejects.toThrow(
      'Identifiants invalides',
    )
  })

  it('retourne authenticated:false quand la session répond 401', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ authenticated: false }),
    })

    await expect(checkSession()).resolves.toEqual({ authenticated: false })
  })

  it('retourne loggedOut:true quand logout répond 401', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    })

    await expect(logoutSession()).resolves.toEqual({ loggedOut: true })
  })
})
