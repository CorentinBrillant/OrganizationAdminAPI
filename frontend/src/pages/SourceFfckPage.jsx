import { useEffect, useMemo } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import UiEmbed from '../components/UiEmbed'
import { setPageFilters } from '../store/campaignsSlice'

export default function SourceFfckPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const ffckRowsByCampaignId = useSelector((state) => state.campaigns.ffckRowsByCampaignId)
  const ffckLatestExportByCampaignId = useSelector((state) => state.campaigns.ffckLatestExportByCampaignId)
  const uiFilters = useSelector((state) => state.campaigns.uiFiltersByPage?.ffck || {})

  const normalizedCampaignId = Number(activeCampaignId)
  const ffckRows = Number.isFinite(normalizedCampaignId)
    ? ffckRowsByCampaignId?.[normalizedCampaignId] || []
    : []
  const ffckExportMeta = Number.isFinite(normalizedCampaignId)
    ? ffckLatestExportByCampaignId?.[normalizedCampaignId] || null
    : null

  const bridgeMessage = useMemo(
    () => ({
      type: 'ffck:activeCampaignContext',
      campaignTitle: String(activeCampaign || '').trim() || null,
      campaignId: Number.isFinite(normalizedCampaignId) ? normalizedCampaignId : null,
      ffckRows,
      ffckExportMeta,
      uiFilters,
    }),
    [activeCampaign, normalizedCampaignId, ffckRows, ffckExportMeta, uiFilters],
  )

  useEffect(() => {
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return
      if (event.data?.type !== 'ffck:uiFiltersChanged' || event.data?.page !== 'ffck') return
      dispatch(setPageFilters({ page: 'ffck', filters: event.data?.filters }))
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [dispatch])

  return <UiEmbed file="source-ffck.html" title="Source FFCK" bridgeMessage={bridgeMessage} />
}
