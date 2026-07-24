import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { fetchHelloAssoLatestItems, importHelloAssoCampaign } from '../api/helloasso'
import { setPageFilters } from '../store/campaignsSlice'
import { calculateHelloAssoKpis, formatApiDateTime, mapHelloAssoItemToRow, sourceColumns } from '../mappers/helloAssoMappers'
import '../styles/sourceHelloAsso.css'

export default function SourceHelloAssoPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const search = useSelector((state) => state.campaigns.uiFiltersByPage?.helloasso?.search || '')
  const campaignId = Number(activeCampaignId)
  const hasCampaign = Number.isFinite(campaignId)
  const [rows, setRows] = useState([])
  const [importMeta, setImportMeta] = useState(null)
  const [columns, setColumns] = useState(sourceColumns)
  const [isLoading, setIsLoading] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncError, setSyncError] = useState('')

  useEffect(() => {
    if (!hasCampaign) {
      setRows([])
      setImportMeta(null)
      return undefined
    }

    const controller = new AbortController()
    setIsLoading(true)
    setSyncError('')
    fetchHelloAssoLatestItems(campaignId, { signal: controller.signal })
      .then(({ items, importMeta: nextImportMeta }) => {
        setRows(items.map(mapHelloAssoItemToRow))
        setImportMeta(nextImportMeta)
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setSyncError(error.message || 'Impossible de charger les données HelloAsso')
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })

    return () => controller.abort()
  }, [campaignId, hasCampaign])

  const filteredRows = rows.filter((row) => Object.values(row).join(' ').toLowerCase().includes(search.trim().toLowerCase()))
  const kpis = calculateHelloAssoKpis(rows)
  const syncLabel = importMeta?.fetched_at
    ? `Dernière synchronisation: ${formatApiDateTime(importMeta.fetched_at)} • ${rows.length} entrées`
    : 'Dernière synchronisation: —'

  function updateColumns(index, direction) {
    const target = index + direction
    if (target < 0 || target >= columns.length) return
    const nextColumns = [...columns]
    ;[nextColumns[index], nextColumns[target]] = [nextColumns[target], nextColumns[index]]
    setColumns(nextColumns)
  }

  function updateCell(rowId, key, value) {
    setRows((currentRows) => currentRows.map((row) => (row.id === rowId ? { ...row, [key]: value } : row)))
  }

  async function sync() {
    if (!hasCampaign || isSyncing) return
    setIsSyncing(true)
    setSyncError('')
    try {
      await importHelloAssoCampaign(campaignId)
      const { items, importMeta: nextImportMeta } = await fetchHelloAssoLatestItems(campaignId)
      setRows(items.map(mapHelloAssoItemToRow))
      setImportMeta(nextImportMeta)
    } catch (error) {
      setSyncError(`Échec de synchronisation (${activeCampaign}) : ${error.message || 'Erreur inconnue'}`)
    } finally {
      setIsSyncing(false)
    }
  }

  return (
    <main className="helloasso-source">
      <section className="helloasso-source-head">
        <div>
          <h1>Flux API HelloAsso</h1>
          <p aria-live="polite">{isSyncing ? `Synchronisation HelloAsso en cours pour "${activeCampaign}"...` : syncLabel}</p>
          {syncError ? <p className="helloasso-source-error" role="alert">{syncError}</p> : null}
        </div>
        <button type="button" className="helloasso-source-button" disabled={!hasCampaign || isSyncing} onClick={sync}>
          {isSyncing ? 'Synchronisation en cours...' : 'Relancer la synchronisation'}
        </button>
      </section>

      <section className="helloasso-source-kpis" aria-label="Indicateurs HelloAsso">
        <article><span>Enregistrements reçus</span><strong>{kpis.received}</strong></article>
        <article><span>Lignes valides</span><strong>{kpis.valid}</strong></article>
        <article><span>Erreurs de mapping</span><strong>{kpis.errors}</strong></article>
      </section>

      <section className="helloasso-source-toolbar">
        <div>
          <input
            type="search"
            value={search}
            placeholder="Filtrer prénom, nom, email, inscription, montant..."
            onChange={(event) => dispatch(setPageFilters({ page: 'helloasso', filters: { search: event.target.value } }))}
          />
          <button type="button" className="btn-subtle" onClick={() => setColumns(sourceColumns)}>Réinitialiser les colonnes</button>
        </div>
        <p>Colonnes: ← et → pour déplacer, × pour supprimer. Double-cliquez une cellule pour l'éditer puis Entrée pour valider.</p>
      </section>

      <section className="helloasso-source-table" aria-busy={isLoading}>
        <table>
          <thead><tr>{columns.map((column, index) => (
            <th key={column.key} scope="col"><div className="helloasso-source-column-head"><span>{column.label}</span><div>
              <button type="button" aria-label={`Déplacer ${column.label} vers la gauche`} disabled={index === 0} onClick={() => updateColumns(index, -1)}>←</button>
              <button type="button" aria-label={`Déplacer ${column.label} vers la droite`} disabled={index === columns.length - 1} onClick={() => updateColumns(index, 1)}>→</button>
              <button type="button" aria-label={`Supprimer ${column.label}`} disabled={columns.length === 1} onClick={() => setColumns(columns.filter((_, columnIndex) => columnIndex !== index))}>×</button>
            </div></div></th>
          ))}</tr></thead>
          <tbody>{isLoading ? <tr><td colSpan={columns.length}>Chargement des données HelloAsso...</td></tr> : null}
          {!isLoading && filteredRows.length === 0 ? <tr><td colSpan={columns.length}>Aucune donnée HelloAsso à afficher.</td></tr> : null}
          {!isLoading && filteredRows.map((row) => <tr key={row.id}>{columns.map((column) => (
            <td
              key={column.key}
              contentEditable
              suppressContentEditableWarning
              onDoubleClick={(event) => event.currentTarget.focus()}
              onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur() } }}
              onBlur={(event) => updateCell(row.id, column.key, event.currentTarget.textContent.trim())}
            >{row[column.key]}</td>
          ))}</tr>)}</tbody>
        </table>
      </section>
    </main>
  )
}
