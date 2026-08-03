import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  fetchCampaignFfckLatestRowsMock,
  fetchCampaignMembersMock,
  fetchHelloAssoLatestItemsMock,
  useSelectorMock,
} = vi.hoisted(() => ({
  fetchCampaignFfckLatestRowsMock: vi.fn(),
  fetchCampaignMembersMock: vi.fn(),
  fetchHelloAssoLatestItemsMock: vi.fn(),
  useSelectorMock: vi.fn(),
}))

vi.mock('react-redux', () => ({
  useSelector: (selector) => useSelectorMock(selector),
}))

vi.mock('../../api/campaigns', () => ({
  fetchCampaignFfckLatestRows: (...args) => fetchCampaignFfckLatestRowsMock(...args),
  fetchCampaignMembers: (...args) => fetchCampaignMembersMock(...args),
}))

vi.mock('../../api/helloasso', () => ({
  fetchHelloAssoLatestItems: (...args) => fetchHelloAssoLatestItemsMock(...args),
}))

import MonitoringCampagnesPage from '../../pages/MonitoringCampagnesPage'

describe('MonitoringCampagnesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSelectorMock.mockImplementation((selector) => selector({
      campaigns: {
        activeCampaignId: 11,
        catalog: [{ id: 11, title: '2026' }],
      },
    }))
    fetchCampaignMembersMock.mockResolvedValue([
      {
        id: 1,
        ffck_licence: 'LIC-OK',
        certificat: 'https://documents.example/certificat.pdf',
        manual_review: true,
      },
      {
        id: 2,
        ffck_licence: 'LIC-MINOR',
        certificat: '',
        autorisation_parentale: '',
        manual_review: false,
        ffck_certificat_expiration: '2026-12-31',
        helloasso_form_slug: 'loisir',
        ffck_licence_type: 'competition',
      },
    ])
    fetchCampaignFfckLatestRowsMock.mockResolvedValue({
      rows: [{ member_id: 2, raw_row: { ddn: '2010-01-01' } }],
      exportMeta: { fetched_at: '2026-08-01T00:00:00Z' },
    })
    fetchHelloAssoLatestItemsMock.mockResolvedValue({
      items: [],
      importMeta: { fetched_at: '2026-08-01T00:00:00Z' },
    })
  })

  it('compte les raisons individuelles et seulement les dossiers conformes', async () => {
    render(<MonitoringCampagnesPage />)

    await waitFor(() => expect(screen.getByText('Monitoring actualisé.')).toBeInTheDocument())

    const cells = screen.getAllByRole('cell')
    expect(cells.map((cell) => cell.textContent)).toContain('1')
    expect(cells.map((cell) => cell.textContent)).toContain('4')
  })
})
