import { useMemo } from 'react'
import { useSelector } from 'react-redux'
import UiEmbed from '../components/UiEmbed'

export default function SourceHelloAssoPage() {
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)

  const bridgeMessage = useMemo(
    () => ({
      type: 'ffck:activeCampaignContext',
      campaignTitle: String(activeCampaign || '').trim() || null,
      campaignId: Number.isFinite(Number(activeCampaignId)) ? Number(activeCampaignId) : null,
    }),
    [activeCampaign, activeCampaignId],
  )

  return <UiEmbed file="source-helloasso.html" title="Source HelloAsso" bridgeMessage={bridgeMessage} />
}
