import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'

import {
  createCampaign as createCampaignRequest,
  fetchCampaignFfckLatestRows,
  fetchCampaignMembers,
  fetchCampaigns,
  saveCampaignManualEdition,
} from '../api/campaigns'

const DEFAULT_CAMPAIGNS = ['2024', '2025', '2026']

const initialState = {
  items: DEFAULT_CAMPAIGNS,
  activeCampaign: DEFAULT_CAMPAIGNS[DEFAULT_CAMPAIGNS.length - 1],
  activeCampaignId: null,
  catalog: [],
  membersByCampaignId: {},
  membersStatusByCampaignId: {},
  membersErrorByCampaignId: {},
  ffckRowsByCampaignId: {},
  ffckRowsStatusByCampaignId: {},
  ffckRowsErrorByCampaignId: {},
  ffckLatestExportByCampaignId: {},
  manualSaveStatusByCampaignId: {},
  manualSaveErrorByCampaignId: {},
  status: 'idle',
  error: null,
}

export const loadCampaigns = createAsyncThunk('campaigns/loadCampaigns', async () => {
  return fetchCampaigns()
})

export const loadCampaignMembers = createAsyncThunk(
  'campaigns/loadCampaignMembers',
  async ({ campaignId }) => {
    const normalizedCampaignId = Number(campaignId)
    const members = await fetchCampaignMembers(normalizedCampaignId)
    return { campaignId: normalizedCampaignId, members }
  },
  {
    condition: ({ campaignId, force = false } = {}, { getState }) => {
      const normalizedCampaignId = Number(campaignId)
      if (!Number.isFinite(normalizedCampaignId)) return false
      if (force) return true

      const state = getState()
      const status = state?.campaigns?.membersStatusByCampaignId?.[normalizedCampaignId]
      const hasCache = Array.isArray(state?.campaigns?.membersByCampaignId?.[normalizedCampaignId])
      if (status === 'loading') return false
      if (status === 'succeeded' && hasCache) return false
      return true
    },
  },
)

export const loadCampaignFfckRows = createAsyncThunk(
  'campaigns/loadCampaignFfckRows',
  async ({ campaignId }) => {
    const normalizedCampaignId = Number(campaignId)
    const result = await fetchCampaignFfckLatestRows(normalizedCampaignId)
    return {
      campaignId: normalizedCampaignId,
      rows: result.rows,
      exportMeta: result.exportMeta,
    }
  },
  {
    condition: ({ campaignId, force = false } = {}, { getState }) => {
      const normalizedCampaignId = Number(campaignId)
      if (!Number.isFinite(normalizedCampaignId)) return false
      if (force) return true

      const state = getState()
      const status = state?.campaigns?.ffckRowsStatusByCampaignId?.[normalizedCampaignId]
      const hasCache = Array.isArray(state?.campaigns?.ffckRowsByCampaignId?.[normalizedCampaignId])
      if (status === 'loading') return false
      if (status === 'succeeded' && hasCache) return false
      return true
    },
  },
)

export const saveCampaignMembersManualEdition = createAsyncThunk(
  'campaigns/saveCampaignMembersManualEdition',
  async ({ campaignId, members }) => {
    const normalizedCampaignId = Number(campaignId)
    const result = await saveCampaignManualEdition(normalizedCampaignId, members)
    return {
      campaignId: normalizedCampaignId,
      last_manual_edition: result.last_manual_edition,
    }
  },
)

export const createCampaign = createAsyncThunk(
  'campaigns/createCampaign',
  async ({ title, status, helloasso_api_key, helloasso_form_slug }) => {
    return createCampaignRequest({ title, status, helloasso_api_key, helloasso_form_slug })
  },
)

const campaignsSlice = createSlice({
  name: 'campaigns',
  initialState,
  reducers: {
    setActiveCampaign(state, action) {
      state.activeCampaign = action.payload
      const active = state.catalog.find((campaign) => campaign.title === state.activeCampaign)
      state.activeCampaignId = active?.id ?? null
    },
    addCampaign(state, action) {
      const campaign = String(action.payload || '').trim()
      if (!campaign) return
      if (!state.items.includes(campaign)) {
        state.items.push(campaign)
      }
      state.activeCampaign = campaign
      state.activeCampaignId = null
    },
    upsertCampaignMemberPatch(state, action) {
      const campaignId = Number(action.payload?.campaignId)
      if (!Number.isFinite(campaignId)) return
      const patch = action.payload?.member
      if (!patch || typeof patch !== 'object') return
      const memberId = Number(patch.id)
      if (!Number.isFinite(memberId)) return

      const current = Array.isArray(state.membersByCampaignId[campaignId])
        ? state.membersByCampaignId[campaignId]
        : []
      const index = current.findIndex((member) => Number(member?.id) === memberId)
      if (index === -1) return

      current[index] = {
        ...current[index],
        ...patch,
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadCampaigns.pending, (state) => {
        state.status = 'loading'
        state.error = null
      })
      .addCase(loadCampaigns.fulfilled, (state, action) => {
        state.status = 'succeeded'
        const nextCatalog = Array.isArray(action.payload) ? action.payload : []
        if (nextCatalog.length === 0) {
          return
        }

        state.catalog = nextCatalog
        const nextCampaigns = [...new Set(nextCatalog.map((campaign) => campaign.title))]
        state.items = nextCampaigns
        if (!nextCampaigns.includes(state.activeCampaign)) {
          state.activeCampaign = nextCampaigns[nextCampaigns.length - 1]
        }
        const active = nextCatalog.find((campaign) => campaign.title === state.activeCampaign)
        state.activeCampaignId = active?.id ?? null
      })
      .addCase(loadCampaigns.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.error.message || 'Impossible de charger les campagnes'
      })
      .addCase(createCampaign.pending, (state) => {
        state.error = null
      })
      .addCase(createCampaign.fulfilled, (state, action) => {
        const campaign = action.payload
        const campaignId = Number(campaign?.id)
        const campaignTitle = String(campaign?.title || '').trim()
        if (!Number.isFinite(campaignId) || !campaignTitle) return

        const existingIndex = state.catalog.findIndex((item) => Number(item?.id) === campaignId)
        if (existingIndex === -1) {
          state.catalog.push(campaign)
        } else {
          state.catalog[existingIndex] = campaign
        }

        state.items = [...new Set(state.catalog.map((item) => item.title))]
        state.activeCampaign = campaignTitle
        state.activeCampaignId = campaignId
      })
      .addCase(createCampaign.rejected, (state, action) => {
        state.error = action.error.message || 'Impossible de créer la campagne'
      })
      .addCase(loadCampaignMembers.pending, (state, action) => {
        const campaignId = Number(action.meta.arg?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.membersStatusByCampaignId[campaignId] = 'loading'
        state.membersErrorByCampaignId[campaignId] = null
      })
      .addCase(loadCampaignMembers.fulfilled, (state, action) => {
        const campaignId = Number(action.payload?.campaignId)
        if (!Number.isFinite(campaignId)) return
        const members = Array.isArray(action.payload?.members) ? action.payload.members : []
        state.membersByCampaignId[campaignId] = members
        state.membersStatusByCampaignId[campaignId] = 'succeeded'
        state.membersErrorByCampaignId[campaignId] = null
      })
      .addCase(loadCampaignMembers.rejected, (state, action) => {
        const campaignId = Number(action.meta.arg?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.membersStatusByCampaignId[campaignId] = 'failed'
        state.membersErrorByCampaignId[campaignId] =
          action.error.message || 'Impossible de charger les membres'
      })
      .addCase(loadCampaignFfckRows.pending, (state, action) => {
        const campaignId = Number(action.meta.arg?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.ffckRowsStatusByCampaignId[campaignId] = 'loading'
        state.ffckRowsErrorByCampaignId[campaignId] = null
      })
      .addCase(loadCampaignFfckRows.fulfilled, (state, action) => {
        const campaignId = Number(action.payload?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.ffckRowsByCampaignId[campaignId] = Array.isArray(action.payload?.rows)
          ? action.payload.rows
          : []
        state.ffckLatestExportByCampaignId[campaignId] =
          action.payload?.exportMeta && typeof action.payload.exportMeta === 'object'
            ? action.payload.exportMeta
            : null
        state.ffckRowsStatusByCampaignId[campaignId] = 'succeeded'
        state.ffckRowsErrorByCampaignId[campaignId] = null
      })
      .addCase(loadCampaignFfckRows.rejected, (state, action) => {
        const campaignId = Number(action.meta.arg?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.ffckRowsStatusByCampaignId[campaignId] = 'failed'
        state.ffckRowsErrorByCampaignId[campaignId] =
          action.error.message || 'Impossible de charger les lignes FFCK'
      })
      .addCase(saveCampaignMembersManualEdition.pending, (state, action) => {
        const campaignId = Number(action.meta.arg?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.manualSaveStatusByCampaignId[campaignId] = 'loading'
        state.manualSaveErrorByCampaignId[campaignId] = null
      })
      .addCase(saveCampaignMembersManualEdition.fulfilled, (state, action) => {
        const campaignId = Number(action.payload?.campaignId)
        if (!Number.isFinite(campaignId)) return
        const lastManualEdition = action.payload?.last_manual_edition || null
        const campaign = state.catalog.find((item) => Number(item?.id) === campaignId)
        if (campaign) {
          campaign.last_manual_edition = lastManualEdition
        }
        state.manualSaveStatusByCampaignId[campaignId] = 'succeeded'
        state.manualSaveErrorByCampaignId[campaignId] = null
      })
      .addCase(saveCampaignMembersManualEdition.rejected, (state, action) => {
        const campaignId = Number(action.meta.arg?.campaignId)
        if (!Number.isFinite(campaignId)) return
        state.manualSaveStatusByCampaignId[campaignId] = 'failed'
        state.manualSaveErrorByCampaignId[campaignId] =
          action.error.message || 'Impossible de sauvegarder les éditions manuelles'
      })
  },
})

export const { setActiveCampaign, addCampaign, upsertCampaignMemberPatch } = campaignsSlice.actions
export default campaignsSlice.reducer
