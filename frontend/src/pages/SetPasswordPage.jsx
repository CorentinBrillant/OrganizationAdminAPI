import { useState } from 'react'

import { clearStoredToken } from '../auth/token'

export default function SetPasswordPage() {
  const [token] = useState(() => {
    const tokenFromFragment = new URLSearchParams(window.location.hash.slice(1)).get('token') || ''
    if (tokenFromFragment) window.history.replaceState({}, '', '/set-password')
    return tokenFromFragment
  })
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (submitting) return
    if (!token) {
      setError('Ce lien est invalide ou incomplet.')
      return
    }
    if (password !== confirmation) {
      setError('Les mots de passe ne correspondent pas.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const response = await fetch('/api/auth/set-password/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password, password_confirmation: confirmation }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.error || 'Impossible de définir le mot de passe.')
      setPassword('')
      setConfirmation('')
      clearStoredToken()
      window.location.replace('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de définir le mot de passe.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="password-link-page">
      <form className="password-link-card" onSubmit={submit}>
        <h1>Définir votre mot de passe</h1>
        <label htmlFor="set-password">Nouveau mot de passe</label>
        <input id="set-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={16} required />
        <label htmlFor="set-password-confirmation">Confirmer le mot de passe</label>
        <input id="set-password-confirmation" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={16} required />
        {error ? <p className="settings-campaign-error">{error}</p> : null}
        <button type="submit" className="btn-subtle" disabled={submitting}>{submitting ? 'Enregistrement...' : 'Définir le mot de passe'}</button>
      </form>
    </main>
  )
}
