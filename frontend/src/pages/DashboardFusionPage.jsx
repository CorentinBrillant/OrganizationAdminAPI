import { useEffect, useMemo, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { withApiAuthHeaders } from '../auth/token'
import {
  loadCampaignMembers,
  saveCampaignMembersManualEdition,
  upsertCampaignMemberPatch,
} from '../store/campaignsSlice'

const sourceColumns = [
  { key: 'statut', label: 'Statut dossier' },
  { key: 'raison', label: 'Raison' },
  { key: 'manual_review', label: 'Vérification manuelle' },
  { key: 'nom', label: 'Nom' },
  { key: 'prenom', label: 'Prénom' },
  { key: 'licence', label: 'Licence FFCK' },
  { key: 'email', label: 'Email' },
  { key: 'certificat', label: 'Certificat' },
  { key: 'autorisation_parentale', label: 'Autorisation parentale' },
  { key: 'photo', label: 'Photo' },
  { key: 'option_ia', label: 'Option IA' },
  { key: 'badge_owned', label: 'Badge possédé' },
  { key: 'badge_ordered', label: 'Badge commandé' },
  { key: 'paiement', label: 'Paiement' },
]

function readCookie(name) {
  const prefix = `${name}=`
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || ''
}

function formatDate(value) {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'medium' }).format(date)
}

function normalize(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

function hasMissingCertificate(row) {
  return !row.certificat_file_uploaded && !String(row.certificat || '').trim()
}

function getRowStatus(row) {
  if (hasMissingCertificate(row)) return 'Bloquant'
  return row.manual_review === 'vérifié' ? 'Conforme' : 'À vérifier'
}

function getRowReason(row) {
  const reasons = []
  if (hasMissingCertificate(row)) reasons.push('Certificat manquant')

  const expiration = new Date(row.ffck_certificat_expiration)
  if (
    row.manual_review !== 'vérifié' &&
    !Number.isNaN(expiration.getTime()) &&
    expiration.getFullYear() === new Date().getFullYear()
  ) {
    reasons.push('Expiration certificat')
  }

  const formSlug = normalize(row.helloasso_form_slug)
  const licenceType = normalize(row.ffck_licence_type)
  if (
    row.manual_review !== 'vérifié' &&
    ((formSlug.includes('loisir') && licenceType.includes('competition')) ||
      (formSlug.includes('competition') && licenceType.includes('loisir')))
  ) {
    reasons.push('Incohérence entre formulaire HelloAsso et type de licence FFCK')
  }

  if (row.manual_review !== 'vérifié' && reasons.length === 0) {
    reasons.push('Vérification manuelle requise')
  }
  return reasons.length ? reasons.join(' | ') : 'Aucune anomalie'
}

function memberToRow(member) {
  const certificateFile = member?.certificat_file || {}
  const row = {
    member_id: Number(member?.id),
    nom: member?.name || '—',
    prenom: member?.first_name || '—',
    licence: member?.ffck_licence || '—',
    email: member?.email || '—',
    certificat: member?.certificat || '',
    certificat_file_uploaded: Boolean(certificateFile.uploaded),
    certificat_file_name: certificateFile.filename || '',
    autorisation_parentale: member?.autorisation_parentale || '',
    photo: member?.photo || '',
    option_ia: member?.option_ia ? 'Oui' : 'Non',
    badge_owned: member?.badge_owned ? 'Oui' : 'Non',
    badge_ordered: member?.badge_ordered ? 'Oui' : 'Non',
    manual_review: member?.manual_review ? 'vérifié' : 'non vérifié',
    paiement: '—',
    ffck_licence_type: member?.ffck_licence_type || '',
    ffck_certificat_expiration: member?.ffck_certificat_expiration || '',
    helloasso_form_slug: member?.helloasso_form_slug || '',
  }
  return { ...row, statut: getRowStatus(row), raison: getRowReason(row) }
}

function rowToPatch(row) {
  const booleanValue = (value) => ['oui', 'vérifié', 'true', '1'].includes(String(value).trim().toLowerCase())
  const optionalLink = (value) => (String(value || '').trim() === '—' ? '' : String(value || '').trim())
  return {
    id: row.member_id,
    first_name: String(row.prenom || '').trim(),
    name: String(row.nom || '').trim(),
    ffck_licence: String(row.licence || '').trim(),
    email: String(row.email || '').trim(),
    certificat: optionalLink(row.certificat),
    autorisation_parentale: optionalLink(row.autorisation_parentale),
    photo: optionalLink(row.photo),
    option_ia: booleanValue(row.option_ia),
    manual_review: booleanValue(row.manual_review),
    badge_owned: booleanValue(row.badge_owned),
    badge_ordered: booleanValue(row.badge_ordered),
  }
}

function badgeClass(status) {
  if (status === 'Conforme' || status === 'vérifié') return 'ok'
  if (status === 'À vérifier' || status === 'non vérifié') return 'warn'
  return 'danger'
}

export default function DashboardFusionPage() {
  const dispatch = useDispatch()
  const fileInputRef = useRef(null)
  const tableScrollTopRef = useRef(null)
  const tableWrapRef = useRef(null)
  const tableRef = useRef(null)
  const [tableWidth, setTableWidth] = useState(0)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const catalog = useSelector((state) => state.campaigns.catalog)
  const members = useSelector((state) => state.campaigns.membersByCampaignId[activeCampaignId] || [])
  const filters = useSelector((state) => state.campaigns.uiFiltersByPage.dashboard)

  const [columns, setColumns] = useState(sourceColumns)
  const [search, setSearch] = useState(filters.search || '')
  const [statusFilter, setStatusFilter] = useState(filters.status || 'all')
  const [reasonFilter, setReasonFilter] = useState(filters.reason || 'all')
  const [ascending, setAscending] = useState(true)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [edits, setEdits] = useState({})
  const [pendingCertificateMemberId, setPendingCertificateMemberId] = useState(null)
  const [busyAction, setBusyAction] = useState('')
  const [message, setMessage] = useState('')

  const activeCatalogItem = catalog.find((campaign) => Number(campaign.id) === Number(activeCampaignId))
  const rows = useMemo(
    () => members.map(memberToRow).map((row) => ({ ...row, ...(edits[row.member_id] || {}) })),
    [members, edits],
  )

  const visibleRows = useMemo(() => {
    const query = search.trim().toLowerCase()
    return rows
      .map((row) => ({ ...row, statut: getRowStatus(row), raison: getRowReason(row) }))
      .filter((row) => {
        const matchesSearch = !query || Object.values(row).join(' ').toLowerCase().includes(query)
        return (
          matchesSearch &&
          (statusFilter === 'all' || row.statut === statusFilter) &&
          (reasonFilter === 'all' || row.raison.includes(reasonFilter))
        )
      })
      .sort((left, right) => (ascending ? 1 : -1) * left.nom.localeCompare(right.nom, 'fr'))
  }, [ascending, reasonFilter, rows, search, statusFilter])

  const kpis = useMemo(
    () => ({
      merged: rows.length,
      exact: rows.filter((row) => getRowStatus(row) === 'Conforme').length,
      critical: rows.filter((row) => getRowStatus(row) === 'Bloquant').length,
      minor: rows.filter((row) => getRowStatus(row) === 'À vérifier').length,
    }),
    [rows],
  )

  useEffect(() => {
    if (Number.isFinite(Number(activeCampaignId))) {
      dispatch(loadCampaignMembers({ campaignId: activeCampaignId }))
    }
    setEdits({})
    setSelectedIds(new Set())
  }, [activeCampaignId, dispatch])

  useEffect(() => {
    setSearch(filters.search || '')
    setStatusFilter(filters.status || 'all')
    setReasonFilter(filters.reason || 'all')
  }, [filters])

  useEffect(() => {
    const table = tableRef.current
    const tableWrap = tableWrapRef.current
    if (!table || !tableWrap) return undefined

    const updateScrollWidth = () => setTableWidth(table.scrollWidth)
    const observer = new ResizeObserver(updateScrollWidth)
    observer.observe(table)
    observer.observe(tableWrap)
    updateScrollWidth()

    return () => observer.disconnect()
  }, [])

  const syncHorizontalScroll = (source) => {
    const topScroll = tableScrollTopRef.current
    const tableWrap = tableWrapRef.current
    if (!topScroll || !tableWrap) return
    if (source === 'top') tableWrap.scrollLeft = topScroll.scrollLeft
    else topScroll.scrollLeft = tableWrap.scrollLeft
  }

  const updateFilters = (next) => {
    dispatch({ type: 'campaigns/setPageFilters', payload: { page: 'dashboard', filters: next } })
  }

  const updateEdit = (memberId, key, value) => {
    setEdits((current) => ({
      ...current,
      [memberId]: { ...(current[memberId] || {}), [key]: value },
    }))
  }

  const saveEdits = async () => {
    const changedRows = rows.filter((row) => edits[row.member_id])
    if (!changedRows.length || !Number.isFinite(Number(activeCampaignId))) return
    setBusyAction('save')
    try {
      await dispatch(
        saveCampaignMembersManualEdition({
          campaignId: activeCampaignId,
          members: changedRows.map(rowToPatch),
        }),
      ).unwrap()
      changedRows.forEach((row) => {
        dispatch(upsertCampaignMemberPatch({ campaignId: activeCampaignId, member: rowToPatch(row) }))
      })
      setEdits({})
      setMessage('Modifications enregistrées.')
    } catch (error) {
      setMessage(error?.message || 'Impossible d’enregistrer les modifications.')
    } finally {
      setBusyAction('')
    }
  }

  const runFusion = async () => {
    if (!Number.isFinite(Number(activeCampaignId))) return
    setBusyAction('fusion')
    setMessage('')
    try {
      const query = `?campaignId=${encodeURIComponent(String(activeCampaignId))}`
      let response = await fetch(`/api/campaigns/sync-members/${query}`, { headers: withApiAuthHeaders() })
      if (response.status === 404) {
        const helloAsso = await fetch(`/api/helloasso/sync-members/${query}`, { headers: withApiAuthHeaders() })
        if (!helloAsso.ok) throw new Error(`HTTP ${helloAsso.status}`)
        response = await fetch(`/api/ffck/sync-members/${query}`, { headers: withApiAuthHeaders() })
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await dispatch(loadCampaignMembers({ campaignId: activeCampaignId, force: true })).unwrap()
      setMessage('Fusion terminée.')
    } catch (error) {
      setMessage(error?.message || 'La fusion a échoué.')
    } finally {
      setBusyAction('')
    }
  }

  const createMember = async () => {
    const firstName = window.prompt('Prénom du nouveau membre ?')
    const name = firstName && window.prompt('Nom du nouveau membre ?')
    const email = name && window.prompt('Email du nouveau membre ?')
    if (!firstName || !name || !email || !Number.isFinite(Number(activeCampaignId))) return
    setBusyAction('create')
    try {
      const csrfToken = readCookie('csrftoken')
      const headers = withApiAuthHeaders({ 'Content-Type': 'application/json' })
      if (csrfToken) headers['X-CSRFToken'] = decodeURIComponent(csrfToken)
      const response = await fetch(`/api/campaigns/${activeCampaignId}/members/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ first_name: firstName.trim(), name: name.trim(), email: email.trim() }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await dispatch(loadCampaignMembers({ campaignId: activeCampaignId, force: true })).unwrap()
    } catch (error) {
      setMessage(error?.message || 'Impossible de créer le membre.')
    } finally {
      setBusyAction('')
    }
  }

  const deleteSelected = async () => {
    if (!selectedIds.size || !Number.isFinite(Number(activeCampaignId))) return
    if (!window.confirm(`Supprimer ${selectedIds.size} membre(s) de la campagne « ${activeCampaign} » ?`)) return
    setBusyAction('delete')
    try {
      const csrfToken = readCookie('csrftoken')
      const headers = withApiAuthHeaders({ 'Content-Type': 'application/json' })
      if (csrfToken) headers['X-CSRFToken'] = decodeURIComponent(csrfToken)
      const response = await fetch(`/api/campaigns/${activeCampaignId}/members/bulk-delete/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ member_ids: [...selectedIds] }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setSelectedIds(new Set())
      await dispatch(loadCampaignMembers({ campaignId: activeCampaignId, force: true })).unwrap()
    } catch (error) {
      setMessage(error?.message || 'Impossible de supprimer la sélection.')
    } finally {
      setBusyAction('')
    }
  }

  const uploadCertificate = async (event) => {
    const file = event.target.files?.[0]
    const memberId = pendingCertificateMemberId
    setPendingCertificateMemberId(null)
    event.target.value = ''
    if (!file || !Number.isFinite(Number(memberId)) || !Number.isFinite(Number(activeCampaignId))) return
    setBusyAction(`upload-${memberId}`)
    try {
      const csrfToken = readCookie('csrftoken')
      const headers = withApiAuthHeaders()
      if (csrfToken) headers['X-CSRFToken'] = decodeURIComponent(csrfToken)
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(`/api/campaigns/${activeCampaignId}/members/${memberId}/certificat-file/`, {
        method: 'POST',
        headers,
        body: form,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await dispatch(loadCampaignMembers({ campaignId: activeCampaignId, force: true })).unwrap()
    } catch (error) {
      setMessage(error?.message || 'Upload du certificat impossible.')
    } finally {
      setBusyAction('')
    }
  }

  const moveColumn = (index, direction) => {
    setColumns((current) => {
      const target = index + direction
      if (target < 0 || target >= current.length) return current
      const next = [...current]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  const allVisibleSelected = visibleRows.length > 0 && visibleRows.every((row) => selectedIds.has(row.member_id))

  return (
    <section className="dashboard-fusion">
      <section className="dashboard-kpis" aria-label="Indicateurs de fusion">
        <article><span>Lignes fusionnées</span><strong>{kpis.merged}</strong></article>
        <article><span>Correspondances exactes</span><strong>{kpis.exact}</strong></article>
        <article><span>Écarts critiques</span><strong>{kpis.critical}</strong></article>
        <article><span>Écarts mineurs</span><strong>{kpis.minor}</strong></article>
      </section>

      <section className="dashboard-panel" aria-label="Tableau consolidé">
        <header className="dashboard-panel-head">
          <div>
            <h1>Consolidation multi-source</h1>
            <p>Dernière fusion : {formatDate(activeCatalogItem?.last_merge)}</p>
            <p>Dernière modification : {formatDate(activeCatalogItem?.last_manual_edition)}</p>
          </div>
          <div className="dashboard-controls">
            <input value={search} type="search" placeholder="Rechercher nom, email, licence..." onChange={(event) => {
              setSearch(event.target.value)
              updateFilters({ search: event.target.value })
            }} />
            <select value={statusFilter} onChange={(event) => {
              setStatusFilter(event.target.value)
              updateFilters({ status: event.target.value })
            }}>
              <option value="all">Tous les statuts</option>
              <option value="Conforme">Conforme</option>
              <option value="À vérifier">À vérifier</option>
              <option value="Bloquant">Bloquant</option>
            </select>
            <select value={reasonFilter} onChange={(event) => {
              setReasonFilter(event.target.value)
              updateFilters({ reason: event.target.value })
            }}>
              <option value="all">Toutes les raisons</option>
              <option value="Certificat manquant">Certificat manquant</option>
              <option value="Expiration certificat">Expiration certificat</option>
              <option value="Incohérence entre formulaire HelloAsso et type de licence FFCK">Incohérence licence</option>
              <option value="Vérification manuelle requise">Vérification manuelle requise</option>
              <option value="Aucune anomalie">Aucune anomalie</option>
            </select>
            <button type="button" className="btn-subtle" onClick={() => setAscending((value) => !value)} title="Trier par nom">{ascending ? 'A-Z' : 'Z-A'}</button>
            <button type="button" className="btn-subtle" disabled={!selectedIds.size || busyAction === 'delete'} onClick={deleteSelected} title="Supprimer la sélection">Supprimer</button>
            <button type="button" className="btn-subtle" disabled={busyAction === 'create'} onClick={createMember} title="Créer un membre">Créer</button>
            {Object.keys(edits).length > 0 && <button type="button" className="btn-subtle" disabled={busyAction === 'save'} onClick={saveEdits}>Sauvegarder</button>}
            <button type="button" disabled={busyAction === 'fusion'} onClick={runFusion} title="Lancer la fusion">{busyAction === 'fusion' ? 'Fusion...' : 'Fusionner'}</button>
            <button type="button" className="btn-subtle" disabled={busyAction === 'refresh'} onClick={async () => {
              setBusyAction('refresh')
              await dispatch(loadCampaignMembers({ campaignId: activeCampaignId, force: true }))
              setBusyAction('')
            }} title="Rafraîchir les membres">Rafraîchir</button>
          </div>
          <p className="dashboard-hint">Colonnes : ← et → pour déplacer, × pour supprimer. Cliquez une cellule pour l’éditer.</p>
          {message && <p className="dashboard-message" role="status">{message}</p>}
        </header>

        <div
          ref={tableScrollTopRef}
          className="dashboard-table-scroll-top"
          aria-hidden="true"
          onScroll={() => syncHorizontalScroll('top')}
        >
          <div style={{ width: tableWidth }} />
        </div>
        <div ref={tableWrapRef} className="dashboard-table-wrap" onScroll={() => syncHorizontalScroll('table')}>
          <table ref={tableRef}>
            <thead>
              <tr>
                <th><input type="checkbox" aria-label="Sélectionner tous les membres visibles" checked={allVisibleSelected} onChange={(event) => {
                  setSelectedIds((current) => {
                    const next = new Set(current)
                    visibleRows.forEach((row) => {
                      if (event.target.checked) next.add(row.member_id)
                      else next.delete(row.member_id)
                    })
                    return next
                  })
                }} /></th>
                {columns.map((column, index) => <th key={column.key}><div className="dashboard-column-head"><span>{column.label}</span><span><button type="button" disabled={index === 0} onClick={() => moveColumn(index, -1)}>←</button><button type="button" disabled={index === columns.length - 1} onClick={() => moveColumn(index, 1)}>→</button><button type="button" disabled={columns.length === 1} onClick={() => setColumns((current) => current.filter((item) => item.key !== column.key))}>×</button></span></div></th>)}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => <tr key={row.member_id}>
                <td><input type="checkbox" aria-label={`Sélectionner ${row.prenom} ${row.nom}`} checked={selectedIds.has(row.member_id)} onChange={(event) => setSelectedIds((current) => {
                  const next = new Set(current)
                  if (event.target.checked) next.add(row.member_id)
                  else next.delete(row.member_id)
                  return next
                })} /></td>
                {columns.map((column) => {
                  const value = row[column.key] ?? ''
                  if (column.key === 'statut' || column.key === 'manual_review') return <td key={column.key}><button type="button" className={`dashboard-badge ${badgeClass(value)}`} onClick={() => column.key === 'manual_review' && updateEdit(row.member_id, 'manual_review', value === 'vérifié' ? 'non vérifié' : 'vérifié')}>{value}</button></td>
                  if (column.key === 'certificat') return <td key={column.key}>{row.certificat ? <a href={row.certificat} target="_blank" rel="noreferrer">Ouvrir</a> : row.certificat_file_uploaded ? <a href={`/api/campaigns/${activeCampaignId}/members/${row.member_id}/certificat-file/download/`} target="_blank" rel="noreferrer">Télécharger {row.certificat_file_name}</a> : <button type="button" className="btn-subtle" disabled={busyAction === `upload-${row.member_id}`} onClick={() => { setPendingCertificateMemberId(row.member_id); fileInputRef.current?.click() }}>Uploader</button>}</td>
                  if (['autorisation_parentale', 'photo'].includes(column.key) && /^https?:\/\//i.test(value)) return <td key={column.key}><a href={value} target="_blank" rel="noreferrer">Ouvrir</a></td>
                  if (['raison'].includes(column.key)) return <td key={column.key}>{value}</td>
                  return <td key={column.key}><input aria-label={`${column.label} pour ${row.prenom} ${row.nom}`} value={value} onChange={(event) => updateEdit(row.member_id, column.key, event.target.value)} /></td>
                })}
              </tr>)}
            </tbody>
          </table>
        </div>
      </section>
      <input ref={fileInputRef} hidden type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={uploadCertificate} />
    </section>
  )
}
