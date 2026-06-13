import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  dispatchMock,
  useDispatchMock,
  useSelectorMock,
  loadCampaignMembersMock,
  setPageFiltersMock,
  uiEmbedSpy,
} = vi.hoisted(() => ({
  dispatchMock: vi.fn(),
  useDispatchMock: vi.fn(),
  useSelectorMock: vi.fn(),
  loadCampaignMembersMock: vi.fn(),
  setPageFiltersMock: vi.fn(),
  uiEmbedSpy: vi.fn(),
}))

useDispatchMock.mockReturnValue(dispatchMock)

vi.mock('react-redux', () => ({
  useDispatch: () => useDispatchMock(),
  useSelector: (selector) => useSelectorMock(selector),
}))

loadCampaignMembersMock.mockImplementation((payload) => ({ type: 'campaigns/loadCampaignMembers', payload }))
setPageFiltersMock.mockImplementation((payload) => ({ type: 'campaigns/setPageFilters', payload }))

vi.mock('../store/campaignsSlice', () => ({
  loadCampaignMembers: (payload) => loadCampaignMembersMock(payload),
  setPageFilters: (payload) => setPageFiltersMock(payload),
}))

vi.mock('../components/UiEmbed', () => ({
  default: (props) => {
    uiEmbedSpy(props)
    return null
  },
}))

import SourceBadgesPage from './SourceBadgesPage'

function createState(overrides = {}) {
  return {
    campaigns: {
      activeCampaign: '2026',
      activeCampaignId: 11,
      uiFiltersByPage: { badges: { search: 'lea' } },
      ...overrides,
    },
  }
}

describe('SourceBadgesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSelectorMock.mockImplementation((selector) => selector(createState()))
  })

  it('passe le bon bridgeMessage à UiEmbed', () => {
    render(<SourceBadgesPage />)

    expect(uiEmbedSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        file: 'source-badges.html',
        title: 'Source Badges',
        bridgeMessage: {
          type: 'ffck:activeCampaignContext',
          campaignTitle: '2026',
          campaignId: 11,
          uiFilters: { search: 'lea' },
        },
      }),
    )
  })

  it('rafraîchit les membres sur message ffck:refreshActiveCampaignMembers', () => {
    render(<SourceBadgesPage />)

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { type: 'ffck:refreshActiveCampaignMembers' },
      }),
    )

    expect(loadCampaignMembersMock).toHaveBeenCalledWith({ campaignId: 11, force: true })
    expect(dispatchMock).toHaveBeenCalledWith({
      type: 'campaigns/loadCampaignMembers',
      payload: { campaignId: 11, force: true },
    })
  })

  it('met à jour les filtres badges quand la page correspond', () => {
    render(<SourceBadgesPage />)

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: {
          type: 'ffck:uiFiltersChanged',
          page: 'badges',
          filters: { search: 'ana' },
        },
      }),
    )

    expect(setPageFiltersMock).toHaveBeenCalledWith({ page: 'badges', filters: { search: 'ana' } })
    expect(dispatchMock).toHaveBeenCalledWith({
      type: 'campaigns/setPageFilters',
      payload: { page: 'badges', filters: { search: 'ana' } },
    })
  })
})
