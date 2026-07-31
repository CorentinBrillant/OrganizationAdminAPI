import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  dispatchMock,
  exportBadgeOrdersMock,
  fetchBadgeLatestRowsMock,
  setPageFiltersMock,
  useDispatchMock,
  useSelectorMock,
} = vi.hoisted(() => ({
  dispatchMock: vi.fn(),
  exportBadgeOrdersMock: vi.fn(),
  fetchBadgeLatestRowsMock: vi.fn(),
  setPageFiltersMock: vi.fn(),
  useDispatchMock: vi.fn(),
  useSelectorMock: vi.fn(),
}))

useDispatchMock.mockReturnValue(dispatchMock)

vi.mock('react-redux', () => ({
  useDispatch: () => useDispatchMock(),
  useSelector: (selector) => useSelectorMock(selector),
}))

vi.mock('../../api/badges', () => ({
  exportBadgeOrders: (...args) => exportBadgeOrdersMock(...args),
  fetchBadgeLatestRows: (...args) => fetchBadgeLatestRowsMock(...args),
  importBadgeFile: vi.fn(),
}))

vi.mock('../../store/campaignsSlice', () => ({
  loadCampaignMembers: vi.fn(),
  setPageFilters: (payload) => {
    setPageFiltersMock(payload)
    return payload
  },
}))

import SourceBadgesPage from '../../pages/SourceBadgesPage'

function createState(overrides = {}) {
  return {
    campaigns: {
      activeCampaign: '2026',
      activeCampaignId: 11,
      uiFiltersByPage: { badges: { search: '' } },
      ...overrides,
    },
  }
}

describe('SourceBadgesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSelectorMock.mockImplementation((selector) => selector(createState()))
    fetchBadgeLatestRowsMock.mockResolvedValue({
      rows: [
        { id: 1, name: 'Durand', first_name: 'Léa', licence: 'A1', badge_owned: true, badge_ordered: false, member_id: 4 },
        { id: 2, name: 'Martin', first_name: 'Noé', licence: 'B2', badge_owned: false, badge_ordered: true, member_id: null },
      ],
      importMeta: { fetched_at: '2026-07-24T10:00:00Z' },
    })
    exportBadgeOrdersMock.mockResolvedValue({ blob: new Blob(['badges']), filename: 'commande.xlsx' })
  })

  it('charge et affiche les lignes, KPI et statut de la campagne active', async () => {
    render(<SourceBadgesPage />)

    await waitFor(() => expect(screen.getByText('Durand')).toBeInTheDocument())
    expect(screen.getByText(/2026 • Dernier import:/)).toBeInTheDocument()
    expect(screen.getByText('2', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getAllByText('1', { selector: 'strong' })).toHaveLength(2)
    expect(fetchBadgeLatestRowsMock).toHaveBeenCalledWith(11, expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('met à jour le filtre badges via le store', async () => {
    render(<SourceBadgesPage />)

    await waitFor(() => expect(screen.getByText('Durand')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText('Rechercher nom, prénom, licence...'), { target: { value: 'lea' } })

    expect(setPageFiltersMock).toHaveBeenCalledWith({ page: 'badges', filters: { search: 'lea' } })
    expect(dispatchMock).toHaveBeenCalledWith({ page: 'badges', filters: { search: 'lea' } })
  })

  it('propose l’export de la commande badges', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:badge-export')
    URL.revokeObjectURL = vi.fn()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<SourceBadgesPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Exporter commande badges' }))

    await waitFor(() => expect(exportBadgeOrdersMock).toHaveBeenCalledWith(11))
    clickSpy.mockRestore()
  })
})
