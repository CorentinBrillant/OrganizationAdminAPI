import { useCallback, useEffect, useState } from 'react'
import { useSelector } from 'react-redux'

import { fetchCampaignFfckLatestRows, fetchCampaignMembers } from '../api/campaigns'
import { fetchHelloAssoLatestItems } from '../api/helloasso'
import { formatApiDateTime } from '../mappers/ffckMappers'
import '../styles/monitoringCampagnes.css'

function campaignStatus(snapshot) {
  const members = snapshot.members || []
  const missingCertificates = members.filter((member) => !member.certificat_file?.uploaded && !member.certificat).length
  const review = members.filter((member) => !member.manual_review).length
  const anomalies = missingCertificates + review
  if (missingCertificates > 0) return { label: 'Bloquée', className: 'danger', completed: members.length - anomalies, anomalies }
  if (review > 0) return { label: 'À contrôler', className: 'warn', completed: members.length - review, anomalies }
  return { label: 'Stable', className: 'ok', completed: members.length, anomalies: 0 }
}

function StatusPill({ status }) {
  return <span className={`monitoring-status ${status.className}`}>{status.label}</span>
}

export default function MonitoringCampagnesPage() {
  const catalog = useSelector((state) => state.campaigns.catalog)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const [snapshots, setSnapshots] = useState({})
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState('Dernière vue stabilisée.')

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setMessage('Lecture des sources et recalcul des indicateurs en cours...')
    const results = await Promise.allSettled(catalog.map(async (campaign) => {
      const [members, helloasso, ffck] = await Promise.all([
        fetchCampaignMembers(campaign.id),
        fetchHelloAssoLatestItems(campaign.id),
        fetchCampaignFfckLatestRows(campaign.id),
      ])
      return [campaign.id, { members, helloasso, ffck }]
    }))
    const nextSnapshots = {}
    for (const result of results) {
      if (result.status === 'fulfilled') {
        const [id, snapshot] = result.value
        nextSnapshots[id] = snapshot
      }
    }
    setSnapshots(nextSnapshots)
    setMessage(results.some((result) => result.status === 'rejected') ? 'Certaines sources n’ont pas pu être chargées.' : 'Monitoring actualisé.')
    setIsLoading(false)
  }, [catalog])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const rows = catalog.map((campaign) => {
    const snapshot = snapshots[campaign.id] || { members: [], helloasso: { items: [], importMeta: null }, ffck: { rows: [], exportMeta: null } }
    return { campaign, snapshot, status: campaignStatus(snapshot) }
  })
  const active = rows.find(({ campaign }) => Number(campaign.id) === Number(activeCampaignId)) || null
  const kpis = {
    open: rows.length,
    stable: rows.filter((row) => row.status.label === 'Stable').length,
    review: rows.filter((row) => row.status.label === 'À contrôler').length,
    blocked: rows.filter((row) => row.status.label === 'Bloquée').length,
  }
  const alerts = active ? [
    !active.snapshot.helloasso.importMeta && 'Synchronisation HelloAsso absente',
    !active.snapshot.ffck.exportMeta && 'Import FFCK non chargé',
    active.status.label === 'Bloquée' && `${active.status.anomalies} anomalie(s) bloquante(s) ouverte(s)`,
  ].filter(Boolean) : []

  function navigate(page) {
    window.dispatchEvent(new MessageEvent('message', { origin: window.location.origin, data: { type: 'ffck:navigate', page } }))
  }

  return (
    <main className="monitoring-page">
      <section className="monitoring-hero">
        <div><p>Vue transverse</p><h1>Monitoring des campagnes</h1><span>Vue de contrôle des sources, rapprochements et points bloquants avant consolidation.</span></div>
        <div className="monitoring-hero-actions">
          <strong>{active ? `${active.campaign.title} · ${active.status.label}` : 'Campagne active —'}</strong>
          <button type="button" disabled={isLoading} onClick={refresh}>{isLoading ? 'Actualisation...' : 'Actualiser le monitoring'}</button>
          <small aria-live="polite">{message}</small>
        </div>
      </section>

      <section className="monitoring-kpis" aria-label="Indicateurs globaux">
        <article><span>Campagnes ouvertes</span><strong>{kpis.open}</strong></article><article><span>Campagnes stables</span><strong>{kpis.stable}</strong></article><article><span>À contrôler</span><strong>{kpis.review}</strong></article><article><span>Bloquées</span><strong>{kpis.blocked}</strong></article>
      </section>

      <section className="monitoring-health-grid">
        <article className="monitoring-card"><div className="monitoring-card-head"><div><h2>État de la campagne active</h2><p>Volumes réellement disponibles et priorité opérationnelle.</p></div>{active ? <StatusPill status={active.status} /> : null}</div>
          <div className="monitoring-metrics"><div><span>Dossiers complets</span><strong>{active?.status.completed || 0}</strong></div><div><span>Anomalies ouvertes</span><strong>{active?.status.anomalies || 0}</strong></div><div><span>Prochaine action</span><strong>{active?.status.label === 'Bloquée' ? 'Corriger les blocages' : active?.status.label === 'À contrôler' ? 'Revoir les écarts' : 'Consolider'}</strong></div></div>
        </article>
        <article className="monitoring-card"><div className="monitoring-card-head"><div><h2>Alertes à traiter</h2><p>Les points empêchant la stabilisation.</p></div></div><div className="monitoring-alerts">{alerts.length ? alerts.map((alert) => <p key={alert}>{alert}</p>) : <p>Aucune alerte pour la campagne active.</p>}</div></article>
      </section>

      <section className="monitoring-timeline">
        <article><h2>Dernière fusion</h2><strong>{formatApiDateTime(active?.campaign.last_merge)}</strong><p>{active ? `${active.status.anomalies} anomalie(s) ouverte(s).` : 'Aucune donnée disponible.'}</p></article>
        <article><h2>Dernière synchro HelloAsso</h2><strong>{formatApiDateTime(active?.snapshot.helloasso.importMeta?.fetched_at)}</strong><p>{active?.snapshot.helloasso.items.length || 0} entrée(s) observée(s).</p></article>
        <article><h2>Dernier import FFCK</h2><strong>{formatApiDateTime(active?.snapshot.ffck.exportMeta?.fetched_at)}</strong><p>{active?.snapshot.ffck.rows.length || 0} ligne(s) importée(s).</p></article>
      </section>

      <section className="monitoring-table-card"><header><div><h2>État des campagnes</h2><p>Synthèse des sources et de la consolidation.</p></div><div><button type="button" className="btn-subtle" onClick={() => navigate('dashboard')}>Voir la fusion</button><button type="button" className="btn-subtle" onClick={() => navigate('helloasso')}>Voir HelloAsso</button></div></header>
        <div className="monitoring-table-wrap"><table><thead><tr><th>Campagne</th><th>Statut global</th><th>Dernière fusion</th><th>HelloAsso</th><th>Import FFCK</th><th>Dossiers complets</th><th>Anomalies</th><th>État</th><th>Accès</th></tr></thead><tbody>
          {rows.length === 0 ? <tr><td colSpan="9">Aucune campagne configurée.</td></tr> : rows.map(({ campaign, snapshot, status }) => <tr key={campaign.id} className={Number(campaign.id) === Number(activeCampaignId) ? 'is-active' : ''}><td><strong>{campaign.title}</strong></td><td><StatusPill status={status} /></td><td>{formatApiDateTime(campaign.last_merge)}</td><td>{formatApiDateTime(snapshot.helloasso.importMeta?.fetched_at)}</td><td>{formatApiDateTime(snapshot.ffck.exportMeta?.fetched_at)}</td><td>{status.completed}</td><td>{status.anomalies}</td><td>Campagne {Number(campaign.id) === Number(activeCampaignId) ? 'active' : 'ouverte'}</td><td><button type="button" className="btn-subtle" onClick={() => navigate('dashboard')}>Fusion</button></td></tr>)}
        </tbody></table></div>
      </section>
    </main>
  )
}
