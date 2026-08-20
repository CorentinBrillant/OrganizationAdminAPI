import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UserManagementPage from '../../pages/UserManagementPage'
import { createAdminUser, fetchAdminUsers, sendPasswordResetLink } from '../../api/adminUsers'

vi.mock('../../api/adminUsers', () => ({
  createAdminUser: vi.fn(),
  fetchAdminUsers: vi.fn(),
  sendPasswordResetLink: vi.fn(),
  sendPasswordSetupLink: vi.fn(),
}))

const definedUser = { id: 1, email: 'jean@example.com', first_name: 'Jean', last_name: 'Dupont', is_active: true, password_status: 'defined' }

describe('UserManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchAdminUsers.mockResolvedValue([definedUser])
  })

  it('creates a user without collecting a password', async () => {
    const user = userEvent.setup()
    createAdminUser.mockResolvedValue({ ...definedUser, id: 2, email: 'new@example.com', password_status: 'pending' })
    render(<UserManagementPage />)
    await screen.findByText('jean@example.com')
    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Prénom'), 'New')
    await user.type(screen.getByLabelText('Nom'), 'User')
    await user.click(screen.getByRole('button', { name: 'Créer le compte' }))
    expect(createAdminUser).toHaveBeenCalledWith(expect.objectContaining({ email: 'new@example.com', send_password_email: true }))
    expect(screen.queryByLabelText('Nouveau mot de passe')).not.toBeInTheDocument()
  })

  it('requires confirmation before sending a reset link', async () => {
    const user = userEvent.setup()
    sendPasswordResetLink.mockResolvedValue(definedUser)
    render(<UserManagementPage />)
    await user.click(await screen.findByText('jean@example.com'))
    await user.click(screen.getByRole('button', { name: 'Réinitialiser le mot de passe' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(sendPasswordResetLink).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Envoyer le lien' }))
    expect(sendPasswordResetLink).toHaveBeenCalledWith(1)
  })
})
