import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  dispatchMock,
  loadCampaignsMock,
  setActiveCampaignMock,
  useDispatchMock,
  useSelectorMock,
} = vi.hoisted(() => ({
  dispatchMock: vi.fn(),
  loadCampaignsMock: vi.fn(() => ({ type: 'campaigns/loadCampaigns' })),
  setActiveCampaignMock: vi.fn((campaign) => ({ type: 'campaigns/setActiveCampaign', payload: campaign })),
  useDispatchMock: vi.fn(),
  useSelectorMock: vi.fn(),
}))

useDispatchMock.mockReturnValue(dispatchMock)

vi.mock('react-redux', () => ({
  useDispatch: () => useDispatchMock(),
  useSelector: (selector) => useSelectorMock(selector),
}))

vi.mock('../../store/campaignsSlice', () => ({
  loadCampaignFfckRows: vi.fn(),
  loadCampaignMembers: vi.fn(),
  loadCampaigns: () => loadCampaignsMock(),
  setActiveCampaign: (campaign) => setActiveCampaignMock(campaign),
}))

import Sidebar from '../../components/Sidebar'

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    useSelectorMock.mockImplementation((selector) =>
      selector({ campaigns: { activeCampaign: '', activeCampaignId: null } }),
    )
  })

  it('restaure la campagne précédemment activée avant de charger le catalogue', () => {
    localStorage.setItem('ffck:campaign', 'Campagne 2025')

    render(<Sidebar activePage="settings" onPageChange={vi.fn()} />)

    expect(setActiveCampaignMock).toHaveBeenCalledWith('Campagne 2025')
    expect(loadCampaignsMock).toHaveBeenCalledOnce()
    expect(dispatchMock).toHaveBeenNthCalledWith(1, {
      type: 'campaigns/setActiveCampaign',
      payload: 'Campagne 2025',
    })
    expect(dispatchMock).toHaveBeenNthCalledWith(2, { type: 'campaigns/loadCampaigns' })
  })
})
