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
    <div className="app-shell login-shell">
      <main className="app-main login-main">
        <form onSubmit={handleSubmit} className="login-form">
          <img className="login-logo" src="/ckcp.png" alt="CKCP" />
          <h1 className="login-title">Connexion</h1>
          <label className="login-field">
            Login
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="login-field">
            Mot de passe
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error ? <p className="login-error">{error}</p> : null}
          <button type="submit" className="login-submit" disabled={submitting}>
            {submitting ? 'Connexion...' : 'Se connecter'}
          </button>
        </form>
      </main>
    </div>
  )
}
