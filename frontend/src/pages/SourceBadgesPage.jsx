import { useEffect, useMemo } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import UiEmbed from '../components/UiEmbed'
import { loadCampaignMembers, setPageFilters } from '../store/campaignsSlice'

export default function SourceBadgesPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const uiFilters = useSelector((state) => state.campaigns.uiFiltersByPage?.badges || {})

  const bridgeMessage = useMemo(
    () => ({
      type: 'ffck:activeCampaignContext',
      campaignTitle: String(activeCampaign || '').trim() || null,
      campaignId: Number.isFinite(Number(activeCampaignId)) ? Number(activeCampaignId) : null,
      uiFilters,
    }),
    [activeCampaign, activeCampaignId, uiFilters],
  )

  useEffect(() => {
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return
      if (event.data?.type === 'ffck:refreshActiveCampaignMembers') {
        const normalizedCampaignId = Number(activeCampaignId)
        if (!Number.isFinite(normalizedCampaignId)) return
        dispatch(loadCampaignMembers({ campaignId: normalizedCampaignId, force: true }))
        return
      }
      if (event.data?.type !== 'ffck:uiFiltersChanged' || event.data?.page !== 'badges') return
      dispatch(setPageFilters({ page: 'badges', filters: event.data?.filters }))
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [dispatch, activeCampaignId])

  return <UiEmbed file="source-badges.html" title="Source Badges" bridgeMessage={bridgeMessage} />
}
