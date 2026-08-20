import { useEffect, useMemo, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { changePassword } from '../api/auth'
import { fetchHelloAssoMembershipForms, updateCampaignSettings } from '../api/campaigns'
import {
  createCampaign,
  loadCampaignFfckRows,
  loadCampaignMembers,
  loadCampaigns,
  setActiveCampaign,
} from '../store/campaignsSlice'

export default function SettingsCampagnePage({ user = null, onLogout = null }) {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const catalog = useSelector((state) => state.campaigns.catalog)
  const campaigns = useSelector((state) => state.campaigns.items)
  const [helloassoFormSlug, setHelloassoFormSlug] = useState('')
  const [error, setError] = useState('')
  const [formsError, setFormsError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [membershipForms, setMembershipForms] = useState([])
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  const selectedCampaign = useMemo(() => {
    const normalizedCampaignId = Number(activeCampaignId)
    if (Number.isFinite(normalizedCampaignId)) {
      return catalog.find((campaign) => Number(campaign?.id) === normalizedCampaignId) || null
    }
    const normalizedTitle = String(activeCampaign || '').trim()
    if (!normalizedTitle) return null
    return catalog.find((campaign) => String(campaign?.title || '').trim() === normalizedTitle) || null
  }, [activeCampaign, activeCampaignId, catalog])

  useEffect(() => {
    const nextSlug =
      selectedCampaign && typeof selectedCampaign.helloasso_form_slug === 'string'
        ? selectedCampaign.helloasso_form_slug
        : ''
    setHelloassoFormSlug(nextSlug)
    setError('')
    setSaved(false)
  }, [selectedCampaign])

  useEffect(() => {
    let cancelled = false
    const loadMembershipForms = async () => {
      try {
        const forms = await fetchHelloAssoMembershipForms()
        if (cancelled) return
        setMembershipForms(forms)
        setFormsError('')
      } catch (err) {
        if (cancelled) return
        setMembershipForms([])
        setFormsError(err instanceof Error ? err.message : 'Impossible de charger les campagnes HelloAsso.')
      }
    }

    loadMembershipForms()
    return () => {
      cancelled = true
    }
  }, [])

  const handleCampaignChange = (event) => {
    const nextCampaign = String(event.target.value || '').trim()
    dispatch(setActiveCampaign(nextCampaign))

    const campaign = catalog.find((item) => item.title === nextCampaign)
    const campaignId = Number(campaign?.id)
    if (Number.isFinite(campaignId)) {
      dispatch(loadCampaignMembers({ campaignId, force: true }))
      dispatch(loadCampaignFfckRows({ campaignId, force: true }))
    }
  }

  const handleAddCampaign = () => {
    const next = window.prompt('Nom de la campagne (ex: 2027)')
    const title = String(next || '').trim()
    if (!title) return
    dispatch(createCampaign({ title }))
      .unwrap()
      .catch(() => {
        window.alert('Impossible de créer la campagne. Vérifie le backend API.')
      })
  }

  const handlePasswordSubmit = async (event) => {
    event.preventDefault()
    if (changingPassword) return

    if (!user?.name) {
      setPasswordError('Le changement de mot de passe requiert une session utilisateur.')
      return
    }
    if (newPassword !== newPasswordConfirmation) {
      setPasswordError('Les nouveaux mots de passe ne correspondent pas.')
      return
    }

    setChangingPassword(true)
    setPasswordError('')
    try {
      await changePassword({ currentPassword, newPassword, newPasswordConfirmation })
      setCurrentPassword('')
      setNewPassword('')
      setNewPasswordConfirmation('')
      await onLogout?.()
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Échec du changement de mot de passe.')
    } finally {
      setChangingPassword(false)
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (saving) return

    const campaignId = Number(selectedCampaign?.id)
    if (!Number.isFinite(campaignId)) {
      setError('Aucune campagne sélectionnée.')
      setSaved(false)
      return
    }

    setSaving(true)
    setError('')
    setSaved(false)
    try {
      await updateCampaignSettings(campaignId, { helloasso_form_slug: helloassoFormSlug })
      await dispatch(loadCampaigns())
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Échec de la sauvegarde.')
      setSaved(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="settings-campaign-page">
      <header>
        <h1 className="settings-campaign-title">Settings Campagne</h1>
        <p className="micro">
          Campagne active: <strong>{selectedCampaign?.title || 'Aucune'}</strong>
        </p>
      </header>

      <section className="settings-campaign-account" aria-labelledby="account-settings-title">
        <h2 id="account-settings-title">Session</h2>
        <div>
          <strong>{user?.name || 'Aucun utilisateur connecté'}</strong>
          {user?.name ? <span>{user.role || 'Connecté'}</span> : null}
        </div>
        <button type="button" className="btn-subtle" onClick={onLogout} disabled={!onLogout}>
          Se déconnecter
        </button>
        <form className="settings-campaign-password" onSubmit={handlePasswordSubmit}>
          <h3>Changer le mot de passe</h3>
          <p className="micro">Cette action déconnectera toutes vos sessions actives.</p>
          <label className="settings-campaign-field" htmlFor="currentPassword">
            Mot de passe actuel
          </label>
          <input
            id="currentPassword"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            required
            disabled={changingPassword || !user?.name}
          />
          <label className="settings-campaign-field" htmlFor="newPassword">
            Nouveau mot de passe
          </label>
          <input
            id="newPassword"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            autoComplete="new-password"
            minLength={16}
            required
            disabled={changingPassword || !user?.name}
          />
          <label className="settings-campaign-field" htmlFor="newPasswordConfirmation">
            Confirmer le nouveau mot de passe
          </label>
          <input
            id="newPasswordConfirmation"
            type="password"
            value={newPasswordConfirmation}
            onChange={(event) => setNewPasswordConfirmation(event.target.value)}
            autoComplete="new-password"
            minLength={16}
            required
            disabled={changingPassword || !user?.name}
          />
          {passwordError ? <p className="settings-campaign-error">{passwordError}</p> : null}
          <div>
            <button type="submit" className="btn-subtle" disabled={changingPassword || !user?.name}>
              {changingPassword ? 'Modification...' : 'Modifier le mot de passe'}
            </button>
          </div>
        </form>
      </section>

      <section className="settings-campaign-management" aria-labelledby="campaign-management-title">
        <h2 id="campaign-management-title">Gestion des campagnes</h2>
        <label className="settings-campaign-field" htmlFor="campaignSelect">
          Campagne active
        </label>
        <select
          id="campaignSelect"
          value={activeCampaign || ''}
          onChange={handleCampaignChange}
        >
          {campaigns.map((campaign) => (
            <option key={campaign} value={campaign}>
              {/^\d{4}$/.test(campaign) ? `Campagne ${campaign}` : campaign}
            </option>
          ))}
        </select>
        <div>
          <button type="button" className="btn-subtle" onClick={handleAddCampaign}>
            Nouvelle campagne
          </button>
        </div>
      </section>

      <form className="settings-campaign-form" onSubmit={handleSubmit}>
        <label className="settings-campaign-field" htmlFor="campaignHelloAssoSelector">
          Campagne HelloAsso (Membership)
        </label>
        <select
          id="campaignHelloAssoSelector"
          value={helloassoFormSlug}
          onChange={(event) => setHelloassoFormSlug(event.target.value)}
        >
          <option value="">Sélectionner une campagne</option>
          {membershipForms.map((form) => (
            <option key={form.form_slug} value={form.form_slug}>
              {form.title ? `${form.title} (${form.form_slug})` : form.form_slug}
            </option>
          ))}
        </select>

        <label className="settings-campaign-field" htmlFor="campaignHelloAssoFormSlug">
          helloasso_form_slug
        </label>
        <input
          id="campaignHelloAssoFormSlug"
          type="text"
          value={helloassoFormSlug}
          onChange={(event) => setHelloassoFormSlug(event.target.value)}
          placeholder="ex: inscriptions-2027"
          autoComplete="off"
        />

        {formsError ? <p className="settings-campaign-error">{formsError}</p> : null}
        {error ? <p className="settings-campaign-error">{error}</p> : null}
        {saved ? <p className="settings-campaign-success">Paramètres enregistrés.</p> : null}

        <div>
          <button type="submit" className="btn-subtle" disabled={saving || !selectedCampaign}>
            {saving ? 'Enregistrement...' : 'Enregistrer'}
          </button>
        </div>
      </form>
    </section>
  )
}
