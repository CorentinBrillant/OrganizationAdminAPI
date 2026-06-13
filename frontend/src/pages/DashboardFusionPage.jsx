import { useEffect, useMemo } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import UiEmbed from '../components/UiEmbed'
import {
  loadCampaignMembers,
  setPageFilters,
  upsertCampaignMemberPatch,
} from '../store/campaignsSlice'

export default function DashboardFusionPage() {
  const dispatch = useDispatch()
  const activeCampaignId = useSelector((state) => state.campaigns.activeCampaignId)
  const activeCampaign = useSelector((state) => state.campaigns.activeCampaign)
  const catalog = useSelector((state) => state.campaigns.catalog)
  const membersByCampaignId = useSelector((state) => state.campaigns.membersByCampaignId)
  const uiFilters = useSelector((state) => state.campaigns.uiFiltersByPage?.dashboard || {})

  useEffect(() => {
    const onMessage = async (event) => {
      if (event.origin !== window.location.origin) return
      if (event.data?.type === 'ffck:memberEdited') {
        const normalizedCampaignId = Number(event.data?.campaignId)
        if (!Number.isFinite(normalizedCampaignId)) return
        dispatch(
          upsertCampaignMemberPatch({
            campaignId: normalizedCampaignId,
            member: event.data?.member,
          }),
        )
        return
      }
      if (event.data?.type === 'ffck:uiFiltersChanged' && event.data?.page === 'dashboard') {
        dispatch(
          setPageFilters({
            page: 'dashboard',
            filters: event.data?.filters,
          }),
        )
        return
      }
      if (event.data?.type !== 'ffck:refreshActiveCampaignMembers') return

      const normalizedCampaignId = Number(activeCampaignId)
      if (!Number.isFinite(normalizedCampaignId)) return

      dispatch(loadCampaignMembers({ campaignId: normalizedCampaignId, force: true }))
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [dispatch, activeCampaignId])

  const bridgeMessage = useMemo(() => {
    const normalizedCampaignId = Number(activeCampaignId)
    const members =
      Number.isFinite(normalizedCampaignId) && Array.isArray(membersByCampaignId[normalizedCampaignId])
        ? membersByCampaignId[normalizedCampaignId]
        : []

    const activeCatalogItem = Number.isFinite(normalizedCampaignId)
      ? catalog.find((campaign) => Number(campaign?.id) === normalizedCampaignId)
      : catalog.find((campaign) => String(campaign?.title || '').trim() === activeCampaign)

    return {
      type: 'ffck:activeCampaignMembers',
      campaignId: Number.isFinite(normalizedCampaignId) ? normalizedCampaignId : null,
      campaignTitle: String(activeCampaign || '').trim() || null,
      members,
      lastMerge: activeCatalogItem?.last_merge || null,
      lastManualEdition: activeCatalogItem?.last_manual_edition || null,
      uiFilters,
    }
  }, [activeCampaignId, activeCampaign, catalog, membersByCampaignId, uiFilters])

  return <UiEmbed file="dashboard-fusion.html" title="Inscriptions" bridgeMessage={bridgeMessage} />
}
