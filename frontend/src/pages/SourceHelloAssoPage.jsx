import { useEffect, useMemo } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import UiEmbed from '../components/UiEmbed'
import { setPageFilters } from '../store/campaignsSlice'

export default function SourceHelloAssoPage() {
  const dispatch = useDispatch()
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const uiFilters = useSelector((state) => state.campaigns.uiFiltersByPage?.helloasso || {})

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
      if (event.data?.type !== 'ffck:uiFiltersChanged' || event.data?.page !== 'helloasso') return
      dispatch(setPageFilters({ page: 'helloasso', filters: event.data?.filters }))
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [dispatch])

  return <UiEmbed file="source-helloasso.html" title="Source HelloAsso" bridgeMessage={bridgeMessage} />
}
