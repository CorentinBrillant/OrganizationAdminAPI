import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import LoginPage from './LoginPage'

describe('LoginPage', () => {
  it('affiche une erreur de validation si login ou mot de passe manquant', async () => {
    const user = userEvent.setup()
    const onLogin = vi.fn()

    render(<LoginPage onLogin={onLogin} />)

    await user.type(screen.getByLabelText('Login'), '   ')
    await user.type(screen.getByLabelText('Mot de passe'), 'secret')
    await user.click(screen.getByRole('button', { name: 'Se connecter' }))

    expect(await screen.findByText('Veuillez renseigner le login et le mot de passe.')).toBeInTheDocument()
    expect(onLogin).not.toHaveBeenCalled()
  })

  it('trim le username et vide le mot de passe après succès', async () => {
    const user = userEvent.setup()
    const onLogin = vi.fn().mockResolvedValue({})

    render(<LoginPage onLogin={onLogin} />)

    await user.type(screen.getByLabelText('Login'), '  admin  ')
    await user.type(screen.getByLabelText('Mot de passe'), 'secret')
    await user.click(screen.getByRole('button', { name: 'Se connecter' }))

    expect(onLogin).toHaveBeenCalledWith({ username: 'admin', password: 'secret' })
    expect(screen.getByLabelText('Mot de passe')).toHaveValue('')
  })

  it('affiche le message d erreur si onLogin rejette', async () => {
    const user = userEvent.setup()
    const onLogin = vi.fn().mockRejectedValue(new Error('Compte bloqué'))

    render(<LoginPage onLogin={onLogin} />)

    await user.type(screen.getByLabelText('Login'), 'admin')
    await user.type(screen.getByLabelText('Mot de passe'), 'secret')
    await user.click(screen.getByRole('button', { name: 'Se connecter' }))

    expect(await screen.findByText('Compte bloqué')).toBeInTheDocument()
  })
})
