import { useEffect, useMemo, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { fetchHelloAssoMembershipForms, updateCampaignSettings } from '../api/campaigns'
import { loadCampaigns } from '../store/campaignsSlice'

export default function SettingsCampagnePage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const catalog = useSelector((state) => state.campaigns.catalog)
  const [helloassoFormSlug, setHelloassoFormSlug] = useState('')
  const [error, setError] = useState('')
  const [formsError, setFormsError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [membershipForms, setMembershipForms] = useState([])

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
