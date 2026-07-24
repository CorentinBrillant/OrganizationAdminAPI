import { useCallback, useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { fetchMemberDuplicateSuggestions, mergeMemberDuplicateSuggestion } from '../api/memberDedup'
import { loadCampaignMembers, setPageFilters } from '../store/campaignsSlice'
import '../styles/memberDedup.css'

function memberLabel(member) {
  return `${member?.first_name || ''} ${member?.name || ''}`.trim() || '—'
}

function normalizedScore(value) {
  const score = Number(value)
  return Number.isFinite(score) ? Math.max(0, Math.min(1, score)) : 0.8
}

export default function MemberDedupPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const minScore = useSelector((state) => state.campaigns.uiFiltersByPage?.dedup?.minScore || '0.80')
  const campaignId = Number(activeCampaignId)
  const hasCampaign = Number.isFinite(campaignId)
  const [suggestions, setSuggestions] = useState([])
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [isLoading, setIsLoading] = useState(false)
  const [isMerging, setIsMerging] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const selectAllRef = useRef(null)

  const loadSuggestions = useCallback(async (refresh = false, signal) => {
    if (!hasCampaign) {
      setSuggestions([])
      setSelectedIds(new Set())
      setStatus('Aucune campagne active')
      return
    }

    setIsLoading(true)
    setError('')
    setStatus(refresh ? 'Analyse en cours...' : 'Chargement...')
    try {
      const result = await fetchMemberDuplicateSuggestions(campaignId, normalizedScore(minScore), { refresh, signal })
      setSuggestions(result.suggestions)
      setSelectedIds((current) => new Set([...current].filter((id) => result.suggestions.some((suggestion) => Number(suggestion?.id) === id))))
      setStatus(refresh && result.generation ? `Analyse terminée: ${result.generation.suggestions_count || 0} suggestion(s)` : `${result.suggestions.length} suggestion(s) chargée(s)`)
    } catch (nextError) {
      if (nextError.name !== 'AbortError') {
        setError(`Échec: ${nextError.message || 'Erreur inconnue'}`)
        setStatus('')
      }
    } finally {
      if (!signal?.aborted) setIsLoading(false)
    }
  }, [campaignId, hasCampaign, minScore])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => void loadSuggestions(false, controller.signal), 0)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [loadSuggestions])

  const suggestionIds = suggestions.map((suggestion) => Number(suggestion?.id)).filter(Number.isFinite)
  const selectedCount = selectedIds.size
  const allSelected = suggestionIds.length > 0 && suggestionIds.every((id) => selectedIds.has(id))
  const partlySelected = !allSelected && suggestionIds.some((id) => selectedIds.has(id))

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = partlySelected
  }, [partlySelected])

  function toggleSuggestion(suggestionId, checked) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (checked) next.add(suggestionId)
      else next.delete(suggestionId)
      return next
    })
  }

  async function mergeSuggestion(suggestionId, keepMemberId) {
    if (!hasCampaign || isMerging || !window.confirm('Confirmer la fusion de ces deux membres ?')) return
    setIsMerging(true)
    setError('')
    setStatus('Fusion en cours...')
    try {
      await mergeMemberDuplicateSuggestion(campaignId, suggestionId, keepMemberId)
      setSelectedIds((current) => {
        const next = new Set(current)
        next.delete(suggestionId)
        return next
      })
      await dispatch(loadCampaignMembers({ campaignId, force: true })).unwrap()
      await loadSuggestions()
      setStatus('Fusion terminée')
    } catch (nextError) {
      setError(`Fusion en échec: ${nextError.message || 'Erreur inconnue'}`)
      setStatus('')
    } finally {
      setIsMerging(false)
    }
  }

  async function mergeSelected() {
    const toMerge = suggestions.filter((suggestion) => selectedIds.has(Number(suggestion?.id)))
    if (toMerge.length === 0 || !window.confirm(`Confirmer la fusion de ${toMerge.length} suggestion(s) sélectionnée(s) ?`)) return

    setIsMerging(true)
    setError('')
    let successCount = 0
    let failureCount = 0
    try {
      for (const [index, suggestion] of toMerge.entries()) {
        const suggestionId = Number(suggestion?.id)
        if (!Number.isFinite(suggestionId)) {
          failureCount += 1
          continue
        }
        setStatus(`Fusion en lot en cours (${index + 1}/${toMerge.length})...`)
        try {
          await mergeMemberDuplicateSuggestion(campaignId, suggestionId, suggestion?.recommended_master_id)
          successCount += 1
          setSelectedIds((current) => {
            const next = new Set(current)
            next.delete(suggestionId)
            return next
          })
        } catch {
          failureCount += 1
        }
      }
      if (successCount > 0) await dispatch(loadCampaignMembers({ campaignId, force: true })).unwrap()
      await loadSuggestions()
      setStatus(failureCount > 0 ? `Fusion en lot partielle: ${successCount} réussie(s), ${failureCount} en échec` : `Fusion en lot terminée: ${successCount} suggestion(s) fusionnée(s)`)
    } finally {
      setIsMerging(false)
    }
  }

  return (
    <main className="member-dedup">
      <section className="member-dedup-panel">
        <h1 className="member-dedup-title">Dédoublonnage des membres</h1>
        <p className="member-dedup-hint">Campagne active: {activeCampaign || '—'}</p>
        <div className="member-dedup-controls">
          <label htmlFor="member-dedup-min-score">Score minimum (0.0-1.0)</label>
          <input id="member-dedup-min-score" type="number" min="0" max="1" step="0.01" disabled={isMerging} value={minScore} onChange={(event) => dispatch(setPageFilters({ page: 'dedup', filters: { minScore: event.target.value } }))} />
          <button type="button" className="member-dedup-primary" disabled={!hasCampaign || isLoading || isMerging} onClick={() => loadSuggestions(true)}>Analyser les doublons</button>
          <button type="button" className="member-dedup-ghost" disabled={!hasCampaign || isLoading || isMerging} onClick={() => loadSuggestions(false)}>Recharger la liste</button>
          <button type="button" className="member-dedup-danger" disabled={isMerging || selectedCount === 0} onClick={mergeSelected}>Fusionner la sélection</button>
          <span className="member-dedup-selected" aria-live="polite">{selectedCount} sélectionnée(s)</span>
          <span className={`member-dedup-status${error ? ' error' : ''}`} role={error ? 'alert' : undefined} aria-live="polite">{error || status}</span>
        </div>
      </section>
      <section className="member-dedup-table" aria-busy={isLoading || isMerging}>
        <table>
          <thead><tr><th className="member-dedup-select"><input ref={selectAllRef} type="checkbox" aria-label="Tout sélectionner" disabled={isMerging || suggestionIds.length === 0} checked={allSelected} onChange={(event) => setSelectedIds(event.target.checked ? new Set(suggestionIds) : new Set())} /></th><th>Score</th><th>Membre A</th><th>Membre B</th><th>Raisons</th><th>Actions</th></tr></thead>
          <tbody>
            {isLoading ? <tr><td colSpan="6" className="member-dedup-empty">Chargement des suggestions...</td></tr> : null}
            {!isLoading && suggestions.length === 0 ? <tr><td colSpan="6" className="member-dedup-empty">Aucune suggestion pour ce score.</td></tr> : null}
            {!isLoading && suggestions.map((suggestion) => {
              const left = suggestion.member_left || {}
              const right = suggestion.member_right || {}
              const suggestionId = Number(suggestion.id)
              const recommendedId = Number(suggestion.recommended_master_id)
              const recommendation = recommendedId === Number(left.id) ? 'A' : recommendedId === Number(right.id) ? 'B' : 'auto'
              return <tr key={suggestionId}><td className="member-dedup-select"><input type="checkbox" aria-label="Sélectionner la suggestion" disabled={isMerging} checked={selectedIds.has(suggestionId)} onChange={(event) => toggleSuggestion(suggestionId, event.target.checked)} /></td><td><span className="member-dedup-score">{Number(suggestion.similarity_score || 0).toFixed(2)}</span></td><td><div className="member-dedup-person"><strong>{memberLabel(left)}</strong><span className="member-dedup-meta">Email: {left.email || '—'}</span><span className="member-dedup-meta">Licence: {left.ffck_licence || '—'}</span></div></td><td><div className="member-dedup-person"><strong>{memberLabel(right)}</strong><span className="member-dedup-meta">Email: {right.email || '—'}</span><span className="member-dedup-meta">Licence: {right.ffck_licence || '—'}</span></div></td><td><div className="member-dedup-reasons">{Array.isArray(suggestion.reasons) && suggestion.reasons.length ? suggestion.reasons.map((reason) => <span key={reason} className="member-dedup-tag">{reason}</span>) : <span className="member-dedup-tag">similaire</span>}</div></td><td><div className="member-dedup-actions"><button type="button" className="member-dedup-primary" disabled={isMerging} onClick={() => mergeSuggestion(suggestionId, recommendedId)}>Fusionner (reco {recommendation})</button><button type="button" disabled={isMerging} onClick={() => mergeSuggestion(suggestionId, left.id)}>Garder A</button><button type="button" disabled={isMerging} onClick={() => mergeSuggestion(suggestionId, right.id)}>Garder B</button></div></td></tr>
            })}
          </tbody>
        </table>
      </section>
    </main>
  )
}
