import { useState } from 'react'

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return

    const normalizedUsername = String(username || '').trim()
    if (!normalizedUsername || !password) {
      setError('Veuillez renseigner le login et le mot de passe.')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      await onLogin({ username: normalizedUsername, password })
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Échec de la connexion.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="app-shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
      <main className="app-main" style={{ maxWidth: 420, width: '100%' }}>
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 12, padding: 20 }}>
          <h1 style={{ margin: 0 }}>Connexion</h1>
          <label>
            Login
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Mot de passe
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error ? <p style={{ margin: 0, color: '#b42318' }}>{error}</p> : null}
          <button type="submit" disabled={submitting}>
            {submitting ? 'Connexion...' : 'Se connecter'}
          </button>
        </form>
      </main>
    </div>
  )
}
