import { useEffect, useEffectEvent, useState } from 'react'

import { createAdminUser, fetchAdminUsers, sendPasswordResetLink, sendPasswordSetupLink } from '../api/adminUsers'

const initialForm = { email: '', first_name: '', last_name: '', send_password_email: true }

export default function UserManagementPage() {
  const [users, setUsers] = useState([])
  const [query, setQuery] = useState('')
  const [form, setForm] = useState(initialForm)
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [confirmReset, setConfirmReset] = useState(false)

  const loadUsers = async (nextQuery = query) => {
    setLoading(true)
    setError('')
    try {
      const nextUsers = await fetchAdminUsers(nextQuery)
      setUsers(nextUsers)
      setSelectedUser((current) => nextUsers.find((user) => user.id === current?.id) || null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de charger les utilisateurs.')
    } finally {
      setLoading(false)
    }
  }

  const loadInitialUsers = useEffectEvent(() => { void loadUsers('') })
  useEffect(() => { loadInitialUsers() }, [])

  const submitCreate = async (event) => {
    event.preventDefault()
    if (creating) return
    setCreating(true)
    setError('')
    setSuccess('')
    try {
      const user = await createAdminUser(form)
      setForm(initialForm)
      setSuccess(form.send_password_email ? 'Utilisateur créé et lien envoyé.' : 'Utilisateur créé.')
      await loadUsers(query)
      setSelectedUser(user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de créer l’utilisateur.')
    } finally {
      setCreating(false)
    }
  }

  const sendSetup = async () => {
    if (!selectedUser || actionLoading) return
    setActionLoading(true)
    setError('')
    try {
      const user = await sendPasswordSetupLink(selectedUser.id)
      setSelectedUser(user)
      setUsers((current) => current.map((item) => (item.id === user.id ? user : item)))
      setSuccess('Un nouveau lien de définition a été envoyé.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible d’envoyer le lien.')
    } finally { setActionLoading(false) }
  }

  const sendReset = async () => {
    if (!selectedUser || actionLoading) return
    setActionLoading(true)
    setError('')
    try {
      const user = await sendPasswordResetLink(selectedUser.id)
      setSelectedUser(user)
      setUsers((current) => current.map((item) => (item.id === user.id ? user : item)))
      setSuccess('Le lien de réinitialisation a été envoyé.')
      setConfirmReset(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible d’envoyer le lien.')
    } finally { setActionLoading(false) }
  }

  return (
    <section className="user-management-page">
      <header><h1>Gestion des utilisateurs</h1><p className="micro">Créez des comptes et gérez les liens de mot de passe sans jamais connaître le secret utilisateur.</p></header>
      {error ? <p className="settings-campaign-error" role="alert">{error}</p> : null}
      {success ? <p className="settings-campaign-success">{success}</p> : null}
      <div className="user-management-grid">
        <form className="user-management-card" onSubmit={submitCreate}>
          <h2>Créer un utilisateur</h2>
          <label htmlFor="new-user-email">Email</label><input id="new-user-email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          <label htmlFor="new-user-first-name">Prénom</label><input id="new-user-first-name" value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} required />
          <label htmlFor="new-user-last-name">Nom</label><input id="new-user-last-name" value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} required />
          <label className="user-management-checkbox"><input type="checkbox" checked={form.send_password_email} onChange={(event) => setForm({ ...form, send_password_email: event.target.checked })} /> Envoyer l’email de définition du mot de passe</label>
          <button type="submit" className="btn-subtle" disabled={creating}>{creating ? 'Création...' : 'Créer le compte'}</button>
        </form>
        <section className="user-management-card">
          <h2>Utilisateurs</h2>
          <form className="user-management-search" onSubmit={(event) => { event.preventDefault(); loadUsers() }}>
            <input aria-label="Rechercher un utilisateur" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher" />
            <button type="submit" className="btn-subtle">Rechercher</button>
          </form>
          {loading ? <p>Chargement...</p> : <div className="user-management-list">{users.map((user) => <button type="button" key={user.id} className={selectedUser?.id === user.id ? 'active' : ''} onClick={() => setSelectedUser(user)}><strong>{user.email}</strong><span>{user.first_name} {user.last_name}</span></button>)}</div>}
        </section>
        <section className="user-management-card user-management-detail">
          <h2>Fiche utilisateur</h2>
          {!selectedUser ? <p>Sélectionnez un utilisateur.</p> : <>
            <strong>{selectedUser.first_name} {selectedUser.last_name}</strong><p>{selectedUser.email}</p>
            <h3>Mot de passe</h3>
            {selectedUser.password_status === 'defined' ? <><p className="user-status-defined">Défini</p><button type="button" className="btn-subtle" onClick={() => setConfirmReset(true)} disabled={actionLoading}>Réinitialiser le mot de passe</button></> : <><p className="user-status-pending">{selectedUser.password_status === 'pending' ? 'En attente de définition' : 'Non défini'}</p><button type="button" className="btn-subtle" onClick={sendSetup} disabled={actionLoading || !selectedUser.is_active}>{actionLoading ? 'Envoi...' : 'Renvoyer le lien'}</button></>}
          </>}
        </section>
      </div>
      {confirmReset && selectedUser ? <div className="user-management-dialog" role="dialog" aria-modal="true" aria-labelledby="reset-title"><div><h2 id="reset-title">Réinitialiser le mot de passe ?</h2><p>Un email sera envoyé à :</p><strong>{selectedUser.email}</strong><p>L’utilisateur pourra choisir un nouveau mot de passe à partir du lien reçu.</p><button type="button" className="btn-subtle" onClick={() => setConfirmReset(false)} disabled={actionLoading}>Annuler</button><button type="button" className="btn-subtle" onClick={sendReset} disabled={actionLoading}>{actionLoading ? 'Envoi...' : 'Envoyer le lien'}</button></div></div> : null}
    </section>
  )
}
