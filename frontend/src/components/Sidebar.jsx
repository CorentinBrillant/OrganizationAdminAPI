import { useEffect, useMemo, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import {
  createCampaign,
  loadCampaignFfckRows,
  loadCampaignMembers,
  loadCampaigns,
  setActiveCampaign,
} from '../store/campaignsSlice'

const THEME_STORE_KEY = 'ffck:theme'
const USER_STORE_KEY = 'ffck:user'
const API_KEY_STORE_KEY = 'ffck:source:helloasso:apiKey'
const CAMPAIGN_STORE_KEY = 'ffck:campaign'

function formatCampaignLabel(value) {
  return /^\d{4}$/.test(value) ? `Campagne ${value}` : value
}

function parseJson(value) {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

export default function Sidebar({ activePage, onPageChange }) {
  const dispatch = useDispatch()
  const campaigns = useSelector((state) => state.campaigns.items)
  const campaignCatalog = useSelector((state) => state.campaigns.catalog)
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)

  const [apiKey, setApiKey] = useState('')
  const [user, setUser] = useState({ name: 'Utilisateur bureau directeur', role: 'Bureau directeur' })
  const [theme, setTheme] = useState('dark')

  useEffect(() => {
    dispatch(loadCampaigns())

    const storedApiKey = localStorage.getItem(API_KEY_STORE_KEY) || ''
    setApiKey(storedApiKey)

    const storedTheme = localStorage.getItem(THEME_STORE_KEY) || 'dark'
    setTheme(storedTheme === 'light' ? 'light' : 'dark')

    const storedUser = parseJson(localStorage.getItem(USER_STORE_KEY) || 'null')
    if (storedUser?.name) {
      setUser({ name: storedUser.name, role: storedUser.role || 'Bureau directeur' })
    } else {
      localStorage.setItem(USER_STORE_KEY, JSON.stringify(user))
    }
  }, [dispatch])

  useEffect(() => {
    const onStorage = () => {
      setApiKey(localStorage.getItem(API_KEY_STORE_KEY) || '')
      const nextTheme = localStorage.getItem(THEME_STORE_KEY) || 'dark'
      setTheme(nextTheme === 'light' ? 'light' : 'dark')
      const nextUser = parseJson(localStorage.getItem(USER_STORE_KEY) || 'null')
      if (nextUser?.name) setUser({ name: nextUser.name, role: nextUser.role || 'Bureau directeur' })
      else setUser(null)
    }

    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const maskedApiKey = useMemo(() => {
    if (!apiKey) return 'Aucune clé enregistrée'
    if (apiKey.length <= 6) return 'Clé enregistrée (••••••)'
    return `Clé enregistrée (${apiKey.slice(0, 3)}••••${apiKey.slice(-3)})`
  }, [apiKey])

  const saveApiKey = () => {
    const value = apiKey.trim()
    if (value) localStorage.setItem(API_KEY_STORE_KEY, value)
    else localStorage.removeItem(API_KEY_STORE_KEY)
    setApiKey(value)
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

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(nextTheme)
    localStorage.setItem(THEME_STORE_KEY, nextTheme)
  }

  useEffect(() => {
    document.documentElement.style.colorScheme = theme
  }, [theme])

  useEffect(() => {
    if (!activeCampaign) return
    localStorage.setItem(CAMPAIGN_STORE_KEY, activeCampaign)
  }, [activeCampaign])

  useEffect(() => {
    if (!activeCampaignId) return
    dispatch(loadCampaignMembers({ campaignId: activeCampaignId }))
    dispatch(loadCampaignFfckRows({ campaignId: activeCampaignId }))
  }, [dispatch, activeCampaignId])

  const handleCampaignChange = (event) => {
    const nextCampaign = String(event.target.value || '').trim()
    dispatch(setActiveCampaign(nextCampaign))

    const selectedCampaign = campaignCatalog.find((campaign) => campaign.title === nextCampaign)
    const selectedCampaignId = Number(selectedCampaign?.id)
    if (Number.isFinite(selectedCampaignId)) {
      dispatch(loadCampaignMembers({ campaignId: selectedCampaignId, force: true }))
      dispatch(loadCampaignFfckRows({ campaignId: selectedCampaignId, force: true }))
    }
  }

  const toggleAuth = () => {
    if (user?.name) {
      localStorage.removeItem(USER_STORE_KEY)
      setUser(null)
      return
    }
    const name = window.prompt('Nom utilisateur')
    if (!name?.trim()) return
    const nextUser = { name: name.trim(), role: 'Bureau directeur' }
    localStorage.setItem(USER_STORE_KEY, JSON.stringify(nextUser))
    setUser(nextUser)
  }

  return (
    <aside className="shared-sidebar">
      <div className="sidebar-main">
        <div className="brand">Suivi des inscriptions</div>
        <nav className="nav" aria-label="Navigation">
          <button
            className={activePage === 'dashboard' ? 'active' : ''}
            type="button"
            onClick={() => onPageChange('dashboard')}
          >
            Inscriptions
          </button>
          <button
            className={activePage === 'helloasso' ? 'active' : ''}
            type="button"
            onClick={() => onPageChange('helloasso')}
          >
            Source HelloAsso
          </button>
          <button
            className={activePage === 'ffck' ? 'active' : ''}
            type="button"
            onClick={() => onPageChange('ffck')}
          >
            Source FFCK
          </button>
          <button
            className={activePage === 'dedup' ? 'active' : ''}
            type="button"
            onClick={() => onPageChange('dedup')}
          >
            Dedoublonnage
          </button>
          <button
            className={activePage === 'monitoring' ? 'active' : ''}
            type="button"
            onClick={() => onPageChange('monitoring')}
          >
            Monitoring des campagnes
          </button>
        </nav>
        <div className="campaign-switch">
          <label htmlFor="campaignSelect">Campagne</label>
          <select
            id="campaignSelect"
            className="campaign-select"
            value={activeCampaign || ''}
            onChange={handleCampaignChange}
          >
            {campaigns.map((campaign) => (
              <option key={campaign} value={campaign}>
                {formatCampaignLabel(campaign)}
              </option>
            ))}
          </select>
          <div className="campaign-actions">
            <button className="btn-subtle" type="button" onClick={handleAddCampaign}>
              Nouvelle campagne
            </button>
          </div>
        </div>
        <div className="aside-tools" aria-label="Préférences utilisateur">
          <button className="theme-toggle" type="button" onClick={toggleTheme}>
            {theme === 'dark' ? 'Activer le mode clair' : 'Activer le mode sombre'}
          </button>
        </div>
      </div>

      <div className="sidebar-footer">
        <section className="source-config" aria-label="Configuration des sources">
          <div className="panel-title">Configuration des sources</div>
          <label className="micro" htmlFor="helloAssoApiKey">Clé API HelloAsso</label>
          <input
            id="helloAssoApiKey"
            type="password"
            placeholder="ha_live_..."
            autoComplete="off"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
          />
          <div className="source-row">
            <button id="saveApiKey" className="btn-subtle" type="button" onClick={saveApiKey}>
              Enregistrer
            </button>
            <span className="micro" aria-live="polite">{maskedApiKey}</span>
          </div>
        </section>
        <div className="identity">
          {user?.name ? (
            <>
              <strong>{user.name}</strong>
              <span>{user.role || 'Connecté'}</span>
            </>
          ) : (
            'Aucun utilisateur connecté'
          )}
        </div>
        <button className="btn-subtle" type="button" onClick={toggleAuth}>
          {user?.name ? 'Se déconnecter' : 'Se connecter'}
        </button>
      </div>
    </aside>
  )
}
