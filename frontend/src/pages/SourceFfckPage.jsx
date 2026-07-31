import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { importCampaignFfckExport } from '../api/campaigns'
import { loadCampaignFfckRows, setPageFilters } from '../store/campaignsSlice'
import { formatApiDateTime, mapFfckRowToSourceRow, sourceColumns } from '../mappers/ffckMappers'
import '../styles/sourceFfck.css'

export default function SourceFfckPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const search = useSelector((state) => state.campaigns.uiFiltersByPage?.ffck?.search || '')
  const campaignId = Number(activeCampaignId)
  const hasCampaign = Number.isFinite(campaignId)
  const ffckRows = useSelector((state) => state.campaigns.ffckRowsByCampaignId?.[campaignId] || [])
  const exportMeta = useSelector((state) => state.campaigns.ffckLatestExportByCampaignId?.[campaignId] || null)
  const loadingStatus = useSelector((state) => state.campaigns.ffckRowsStatusByCampaignId?.[campaignId])
  const loadingError = useSelector((state) => state.campaigns.ffckRowsErrorByCampaignId?.[campaignId])
  const [rows, setRows] = useState([])
  const [columns, setColumns] = useState(sourceColumns)
  const [isImporting, setIsImporting] = useState(false)
  const [importError, setImportError] = useState('')

  useEffect(() => {
    setRows(ffckRows.map(mapFfckRowToSourceRow))
  }, [ffckRows])

  const filteredRows = rows.filter((row) => Object.values(row).join(' ').toLowerCase().includes(search.trim().toLowerCase()))
  const fileLabel = exportMeta?.filename
    ? `Fichier chargé: ${exportMeta.filename} (${formatApiDateTime(exportMeta.fetched_at)})${Number.isFinite(Number(exportMeta.rows_count)) ? ` • ${exportMeta.rows_count} lignes` : ''}`
    : 'Fichier chargé: —'
  const error = importError || loadingError

  function renderCell(row, column) {
    if (column.key !== 'photo_ffck') return row[column.key]
    if (!row.photo_ffck) return '—'

    return (
      <a href={`/api/ffck/rows/${row.id}/photo/download/`} target="_blank" rel="noreferrer">
        Télécharger
      </a>
    )
  }

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

  async function importLatestExport() {
    if (!hasCampaign || isImporting) return
    setIsImporting(true)
    setImportError('')
    try {
      await importCampaignFfckExport(campaignId)
      await dispatch(loadCampaignFfckRows({ campaignId, force: true })).unwrap()
    } catch (nextError) {
      setImportError(`Échec de l'import FFCK (${activeCampaign}) : ${nextError.message || 'Erreur inconnue'}`)
    } finally {
      setIsImporting(false)
    }
  }

  return (
    <main className="ffck-source">
      <section className="ffck-source-head">
        <div>
          <h1>Import Excel FFCK</h1>
          <p aria-live="polite">{isImporting ? `Import FFCK en cours pour "${activeCampaign}"...` : fileLabel}</p>
          {error ? <p className="ffck-source-error" role="alert">{error}</p> : null}
        </div>
        <button type="button" className="ffck-source-import" disabled={!hasCampaign || isImporting} onClick={importLatestExport}>
          {isImporting ? 'Import en cours...' : 'Importer un nouveau fichier'}
        </button>
      </section>

      <section className="ffck-source-kpis" aria-label="Indicateurs FFCK">
        <article><span>Lignes importées</span><strong>{rows.length}</strong></article>
        <article><span>Licences reconnues</span><strong>{rows.length}</strong></article>
        <article><span>Anomalies détectées</span><strong>0</strong></article>
      </section>

      <section className="ffck-source-toolbar">
        <div>
          <input
            type="search"
            value={search}
            placeholder="Rechercher licence, nom, catégorie..."
            onChange={(event) => dispatch(setPageFilters({ page: 'ffck', filters: { search: event.target.value } }))}
          />
          <button type="button" className="btn-subtle" onClick={() => setColumns(sourceColumns)}>Réinitialiser les colonnes</button>
        </div>
        <p>Colonnes: ← et → pour déplacer, × pour supprimer. Double-cliquez une cellule pour l'éditer puis Entrée pour valider.</p>
      </section>

      <section className="ffck-source-table" aria-busy={loadingStatus === 'loading' || isImporting}>
        <table>
          <thead><tr>{columns.map((column, index) => (
            <th key={column.key} scope="col"><div className="ffck-source-column-head"><span>{column.label}</span><div>
              <button type="button" aria-label={`Déplacer ${column.label} vers la gauche`} disabled={index === 0} onClick={() => updateColumns(index, -1)}>←</button>
              <button type="button" aria-label={`Déplacer ${column.label} vers la droite`} disabled={index === columns.length - 1} onClick={() => updateColumns(index, 1)}>→</button>
              <button type="button" aria-label={`Supprimer ${column.label}`} disabled={columns.length === 1} onClick={() => setColumns(columns.filter((_, columnIndex) => columnIndex !== index))}>×</button>
            </div></div></th>
          ))}</tr></thead>
          <tbody>{loadingStatus === 'loading' ? <tr><td colSpan={columns.length}>Chargement des données FFCK...</td></tr> : null}
          {loadingStatus !== 'loading' && filteredRows.length === 0 ? <tr><td colSpan={columns.length}>Aucune donnée FFCK à afficher.</td></tr> : null}
          {loadingStatus !== 'loading' && filteredRows.map((row) => <tr key={row.id}>{columns.map((column) => (
            <td
              key={column.key}
              contentEditable={column.key !== 'photo_ffck'}
              suppressContentEditableWarning
              onDoubleClick={(event) => event.currentTarget.focus()}
              onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur() } }}
              onBlur={(event) => updateCell(row.id, column.key, event.currentTarget.textContent.trim())}
            >{renderCell(row, column)}</td>
          ))}</tr>)}</tbody>
        </table>
      </section>
    </main>
  )
}
