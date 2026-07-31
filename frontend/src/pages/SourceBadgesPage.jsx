import { useCallback, useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { exportBadgeOrders, fetchBadgeLatestRows, importBadgeFile } from '../api/badges'
import { loadCampaignMembers, setPageFilters } from '../store/campaignsSlice'
import { formatApiDateTime } from '../mappers/ffckMappers'
import '../styles/sourceBadges.css'

function BadgePill({ value }) {
  return <span className={`badges-source-pill ${value ? 'ok' : 'warn'}`}>{value ? 'Oui' : 'Non'}</span>
}

export default function SourceBadgesPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const search = useSelector((state) => state.campaigns.uiFiltersByPage?.badges?.search || '')
  const campaignId = Number(activeCampaignId)
  const hasCampaign = Number.isFinite(campaignId)
  const inputRef = useRef(null)
  const [rows, setRows] = useState([])
  const [importMeta, setImportMeta] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [error, setError] = useState('')

  const loadRows = useCallback(async (signal) => {
    if (!hasCampaign) {
      setRows([])
      setImportMeta(null)
      return
    }

    setIsLoading(true)
    setError('')
    try {
      const latest = await fetchBadgeLatestRows(campaignId, { signal })
      setRows(latest.rows)
      setImportMeta(latest.importMeta)
    } catch (nextError) {
      if (nextError.name !== 'AbortError') setError(`Erreur chargement badges: ${nextError.message || 'Erreur inconnue'}`)
    } finally {
      if (!signal?.aborted) setIsLoading(false)
    }
  }, [campaignId, hasCampaign])

  useEffect(() => {
    const controller = new AbortController()
    void loadRows(controller.signal)
    return () => controller.abort()
  }, [loadRows])

  const filteredRows = rows.filter((row) => [row.name, row.first_name, row.licence].some((value) => String(value || '').toLowerCase().includes(search.trim().toLowerCase())))
  const status = !hasCampaign
    ? 'Aucune campagne sélectionnée'
    : importMeta?.fetched_at
      ? `${activeCampaign || 'Campagne'} • Dernier import: ${formatApiDateTime(importMeta.fetched_at)} • ${rows.length} ligne(s)`
      : `${activeCampaign || 'Campagne'} • Aucun import badge`

  async function handleFileChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !hasCampaign || isImporting) return

    setIsImporting(true)
    setError('')
    try {
      await importBadgeFile(campaignId, file)
      await dispatch(loadCampaignMembers({ campaignId, force: true })).unwrap()
      await loadRows()
    } catch (nextError) {
      setError(`Échec import badges: ${nextError.message || 'Erreur inconnue'}`)
    } finally {
      setIsImporting(false)
    }
  }

  async function handleExport() {
    if (!hasCampaign || isExporting) return

    setIsExporting(true)
    setError('')
    try {
      const { blob, filename } = await exportBadgeOrders(campaignId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (nextError) {
      setError(`Échec export badges: ${nextError.message || 'Erreur inconnue'}`)
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <main className="badges-source">
      <section className="badges-source-panel">
        <div className="badges-source-head">
          <div>
            <h1 className="badges-source-title">Source Badges</h1>
            <p className={`badges-source-meta${error ? ' error' : ''}`} role={error ? 'alert' : undefined} aria-live="polite">
              {isImporting ? 'Import badges en cours...' : isExporting ? 'Export badges en cours...' : error || status}
            </p>
          </div>
          <button type="button" className="badges-source-import" disabled={!hasCampaign || isImporting} onClick={() => inputRef.current?.click()}>
            Importer Excel badges
          </button>
          <button type="button" className="badges-source-export" disabled={!hasCampaign || isExporting} onClick={handleExport}>
            {isExporting ? 'Export en cours...' : 'Exporter commande badges'}
          </button>
          <input ref={inputRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={handleFileChange} />
        </div>
        <div className="badges-source-toolbar">
          <input
            type="search"
            placeholder="Rechercher nom, prénom, licence..."
            value={search}
            onChange={(event) => dispatch(setPageFilters({ page: 'badges', filters: { search: event.target.value } }))}
          />
          <button type="button" className="btn-subtle" disabled={isLoading || isImporting} onClick={() => loadRows()}>
            Rafraîchir
          </button>
        </div>
      </section>

      <section className="badges-source-kpis" aria-label="KPI badges">
        <article><span>Lignes importées</span><strong>{filteredRows.length}</strong></article>
        <article><span>Badge possédé</span><strong>{filteredRows.filter((row) => row.badge_owned).length}</strong></article>
        <article><span>Badge commandé</span><strong>{filteredRows.filter((row) => row.badge_ordered).length}</strong></article>
      </section>

      <section className="badges-source-table" aria-busy={isLoading || isImporting}>
        <table>
          <thead><tr><th>Nom</th><th>Prénom</th><th>Licence</th><th>Possédé</th><th>Commandé</th><th>Lié membre</th></tr></thead>
          <tbody>
            {isLoading ? <tr><td colSpan="6">Chargement des badges...</td></tr> : null}
            {!isLoading && filteredRows.length === 0 ? <tr><td colSpan="6">Aucune donnée badge à afficher.</td></tr> : null}
            {!isLoading && filteredRows.map((row) => <tr key={row.id}><td>{row.name || '—'}</td><td>{row.first_name || '—'}</td><td>{row.licence || '—'}</td><td><BadgePill value={row.badge_owned} /></td><td><BadgePill value={row.badge_ordered} /></td><td>{Number.isFinite(Number(row.member_id)) ? 'Oui' : 'Non'}</td></tr>)}
          </tbody>
        </table>
      </section>
    </main>
  )
}
