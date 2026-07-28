import { beforeEach, describe, expect, it, vi } from 'vitest'

const { withApiAuthHeadersMock } = vi.hoisted(() => ({
  withApiAuthHeadersMock: vi.fn((headers = {}) => ({
    Authorization: 'Bearer test-token',
    ...headers,
  })),
}))

vi.mock('../../auth/token', () => ({
  withApiAuthHeaders: withApiAuthHeadersMock,
}))

import { changePassword, checkSession, loginWithPassword, logoutSession } from '../../api/auth'

describe('auth api', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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

  it('envoie le changement de mot de passe avec la session authentifiée', async () => {
    vi.spyOn(document, 'cookie', 'get').mockReturnValue('csrftoken=test-csrf-token')
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ password_changed: true }),
    })

    await expect(
      changePassword({
        currentPassword: 'ancien-mot-de-passe',
        newPassword: 'Nouveau-mot-de-passe-123',
        newPasswordConfirmation: 'Nouveau-mot-de-passe-123',
      }),
    ).resolves.toEqual({ passwordChanged: true })

    expect(global.fetch).toHaveBeenCalledWith('/api/auth/password/', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer test-token',
        'Content-Type': 'application/json',
        'X-CSRFToken': 'test-csrf-token',
      },
      body: JSON.stringify({
        current_password: 'ancien-mot-de-passe',
        new_password: 'Nouveau-mot-de-passe-123',
        new_password_confirmation: 'Nouveau-mot-de-passe-123',
      }),
    })
  })
})
