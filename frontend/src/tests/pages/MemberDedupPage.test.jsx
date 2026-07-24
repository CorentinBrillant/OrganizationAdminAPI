import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  dispatchMock,
  fetchMemberDuplicateSuggestionsMock,
  loadCampaignMembersMock,
  mergeMemberDuplicateSuggestionMock,
  setPageFiltersMock,
  useDispatchMock,
  useSelectorMock,
} = vi.hoisted(() => ({
  dispatchMock: vi.fn(),
  fetchMemberDuplicateSuggestionsMock: vi.fn(),
  loadCampaignMembersMock: vi.fn(),
  mergeMemberDuplicateSuggestionMock: vi.fn(),
  setPageFiltersMock: vi.fn(),
  useDispatchMock: vi.fn(),
  useSelectorMock: vi.fn(),
}))

useDispatchMock.mockReturnValue(dispatchMock)

vi.mock('react-redux', () => ({
  useDispatch: () => useDispatchMock(),
  useSelector: (selector) => useSelectorMock(selector),
}))

vi.mock('../../api/memberDedup', () => ({
  fetchMemberDuplicateSuggestions: (...args) => fetchMemberDuplicateSuggestionsMock(...args),
  mergeMemberDuplicateSuggestion: (...args) => mergeMemberDuplicateSuggestionMock(...args),
}))

vi.mock('../../store/campaignsSlice', () => ({
  loadCampaignMembers: (...args) => loadCampaignMembersMock(...args),
  setPageFilters: (payload) => {
    setPageFiltersMock(payload)
    return payload
  },
}))

import MemberDedupPage from '../../pages/MemberDedupPage'

const suggestions = [{
  id: 5,
  similarity_score: 0.91,
  reasons: ['email'],
  recommended_master_id: 1,
  member_left: { id: 1, first_name: 'Léa', name: 'Durand', email: 'lea@example.test', ffck_licence: 'A1' },
  member_right: { id: 2, first_name: 'Lea', name: 'Durand', email: 'lea@example.test', ffck_licence: 'B2' },
}]

function createState() {
  return {
    campaigns: {
      activeCampaign: '2026',
      activeCampaignId: 11,
      uiFiltersByPage: { dedup: { minScore: '0.80' } },
    },
  }
}

describe('MemberDedupPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('confirm', vi.fn(() => true))
    useSelectorMock.mockImplementation((selector) => selector(createState()))
    dispatchMock.mockImplementation(() => ({ unwrap: () => Promise.resolve() }))
    fetchMemberDuplicateSuggestionsMock.mockResolvedValue({ suggestions, generation: null })
    mergeMemberDuplicateSuggestionMock.mockResolvedValue({})
    loadCampaignMembersMock.mockImplementation((payload) => ({ type: 'members/reload', payload }))
  })

  it('charge les suggestions de la campagne active et persiste le score dans Redux', async () => {
    render(<MemberDedupPage />)

    await waitFor(() => expect(screen.getByText('Léa Durand')).toBeInTheDocument())
    expect(fetchMemberDuplicateSuggestionsMock).toHaveBeenCalledWith(11, 0.8, expect.objectContaining({ refresh: false, signal: expect.any(AbortSignal) }))

    fireEvent.change(screen.getByLabelText('Score minimum (0.0-1.0)'), { target: { value: '0.85' } })
    expect(setPageFiltersMock).toHaveBeenCalledWith({ page: 'dedup', filters: { minScore: '0.85' } })
  })

  it('sélectionne et fusionne les suggestions puis rafraîchit les membres', async () => {
    render(<MemberDedupPage />)

    await waitFor(() => expect(screen.getByText('Léa Durand')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Tout sélectionner'))
    expect(screen.getByText('1 sélectionnée(s)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Fusionner la sélection' }))

    await waitFor(() => expect(mergeMemberDuplicateSuggestionMock).toHaveBeenCalledWith(11, 5, 1))
    expect(loadCampaignMembersMock).toHaveBeenCalledWith({ campaignId: 11, force: true })
  })
})
