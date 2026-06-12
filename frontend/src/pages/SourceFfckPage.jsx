import { useMemo } from 'react'
import { useSelector } from 'react-redux'

import UiEmbed from '../components/UiEmbed'

export default function SourceFfckPage() {
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const ffckRowsByCampaignId = useSelector((state) => state.campaigns.ffckRowsByCampaignId)
  const ffckLatestExportByCampaignId = useSelector((state) => state.campaigns.ffckLatestExportByCampaignId)

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
    }),
    [activeCampaign, normalizedCampaignId, ffckRows, ffckExportMeta],
  )

  return <UiEmbed file="source-ffck.html" title="Source FFCK" bridgeMessage={bridgeMessage} />
}
