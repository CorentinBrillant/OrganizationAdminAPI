import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SetPasswordPage from '../../pages/SetPasswordPage'

describe('SetPasswordPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.history.replaceState({}, '', '/')
  })

  it('efface le jeton local après la définition du mot de passe', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/set-password#token=valid-token')
    window.localStorage.setItem('organization_admin_api_token', 'existing-session-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(<SetPasswordPage />)
    expect(window.location.pathname).toBe('/set-password')
    expect(window.location.hash).toBe('')
    await user.type(screen.getByLabelText('Nouveau mot de passe'), 'A-secure-password-123')
    await user.type(screen.getByLabelText('Confirmer le mot de passe'), 'A-secure-password-123')
    await user.click(screen.getByRole('button', { name: 'Définir le mot de passe' }))

    await waitFor(() => {
      expect(window.localStorage.getItem('organization_admin_api_token')).toBeNull()
    })
  })
})
