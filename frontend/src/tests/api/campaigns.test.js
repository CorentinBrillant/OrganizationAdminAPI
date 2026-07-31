import { beforeEach, describe, expect, it, vi } from 'vitest'

const { withApiAuthHeadersMock } = vi.hoisted(() => ({
  withApiAuthHeadersMock: vi.fn((headers = {}) => ({
    Authorization: 'Bearer test-token',
    ...headers,
  })),
}))

vi.mock('../../auth/token', () => ({
  withApiAuthHeaders: withApiAuthHeadersMock,
}))

import {
  createCampaign,
  exportCampaignMembers,
  fetchCampaignFfckLatestRows,
  importCampaignFfckExport,
  fetchCampaignMembers,
  fetchCampaigns,
  fetchHelloAssoMembershipForms,
  saveCampaignManualEdition,
} from '../../api/campaigns'

async function clearTestCookie(name) {
  if (globalThis.cookieStore && typeof globalThis.cookieStore.delete === 'function') {
    await globalThis.cookieStore.delete(name)
    return
  }
  // biome-ignore lint/suspicious/noDocumentCookie: JSDOM fallback when Cookie Store API is unavailable.
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`
}

async function setTestCookie(name, value) {
  if (globalThis.cookieStore && typeof globalThis.cookieStore.set === 'function') {
    await globalThis.cookieStore.set({ name, value, path: '/', sameSite: 'lax' })
    return
  }
  // biome-ignore lint/suspicious/noDocumentCookie: JSDOM fallback when Cookie Store API is unavailable.
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; SameSite=Lax`
}

describe('campaigns api', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
    await clearTestCookie('csrftoken')
  })

  it('normalise la liste des campagnes et filtre les entrées invalides', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        campaigns: [
          { id: '11', title: ' 2026 ', last_merge: '2026-01-01', last_manual_edition: ' ' },
          { id: 'not-a-number', title: '2027' },
          { id: 12, title: '   ' },
        ],
      }),
    })

    const result = await fetchCampaigns()

    expect(result).toEqual([
      {
        id: 11,
        title: '2026',
        last_merge: '2026-01-01',
        last_manual_edition: null,
        helloasso_form_slug: '',
      },
    ])
    expect(global.fetch).toHaveBeenCalledWith('/api/campaigns/', {
      headers: { Authorization: 'Bearer test-token' },
    })
  })

  it('crée une campagne en ajoutant le csrf token quand disponible', async () => {
    await setTestCookie('csrftoken', 'csrf-value')
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        campaign: {
          id: '42',
          title: '  Campagne 2027  ',
          last_merge: '',
          last_manual_edition: '2026-05-01T10:00:00Z',
        },
      }),
    })

    const result = await createCampaign({ title: '  Campagne 2027  ', status: 'active' })

    expect(result).toEqual({
      id: 42,
      title: 'Campagne 2027',
      last_merge: null,
      last_manual_edition: '2026-05-01T10:00:00Z',
    })

    expect(global.fetch).toHaveBeenCalledWith('/api/campaigns/', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer test-token',
        'Content-Type': 'application/json',
        'X-CSRFToken': 'csrf-value',
      },
      body: JSON.stringify({
        title: 'Campagne 2027',
        status: 'active',
        helloasso_api_key: '',
        helloasso_form_slug: '',
      }),
    })
  })

  it('retourne un tableau vide si campaignId est invalide pour les membres', async () => {
    const result = await fetchCampaignMembers('abc')

    expect(result).toEqual([])
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it("conserve le chemin de photo FFCK retourne par l'API", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        rows: [
          {
            id: 7,
            row_index: 1,
            licence: 'FFCK-7',
            nom: 'Alice Martin',
            categorie: 'Senior',
            certificat: 'Loisir',
            photo: 'members/ffck_photos/FFCK-7.jpg',
            member_id: null,
            raw_row: {},
          },
        ],
        export: null,
      }),
    })

    await expect(fetchCampaignFfckLatestRows(42)).resolves.toMatchObject({
      rows: [
        {
          id: 7,
          photo: 'members/ffck_photos/FFCK-7.jpg',
        },
      ],
    })
  })

  it('exporte les lignes affichées en XLSX avec le jeton CSRF', async () => {
    await setTestCookie('csrftoken', 'csrf-value')
    const blob = new Blob(['xlsx'])
    global.fetch.mockResolvedValue({
      ok: true,
      headers: new Headers({ 'Content-Disposition': 'attachment; filename="inscriptions-42.xlsx"' }),
      blob: async () => blob,
    })

    await expect(
      exportCampaignMembers(42, { headers: ['Nom'], rows: [['Durand']] }),
    ).resolves.toEqual({ blob, filename: 'inscriptions-42.xlsx' })
    expect(global.fetch).toHaveBeenCalledWith('/api/campaigns/42/members/export/', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer test-token',
        'Content-Type': 'application/json',
        'X-CSRFToken': 'csrf-value',
      },
      body: JSON.stringify({ headers: ['Nom'], rows: [['Durand']] }),
    })
  })

  it('rejette la sauvegarde manuelle si campaignId n est pas un nombre', async () => {
    await expect(saveCampaignManualEdition('not-a-number', [])).rejects.toThrow('campaignId must be a number')
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('propage le détail de l’erreur HelloAsso', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ error: 'HelloAsso network error: certificate verify failed' }),
    })

    await expect(fetchHelloAssoMembershipForms()).rejects.toThrow(
      'HelloAsso network error: certificate verify failed',
    )
  })

  it('importe un export FFCK authentifié et retourne ses métadonnées', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      headers: new Headers({
        'Content-Disposition': 'attachment; filename="licences.xlsx"',
        'X-FFCK-Rows-Count': '17',
      }),
      arrayBuffer: async () => new ArrayBuffer(0),
    })

    await expect(importCampaignFfckExport(42)).resolves.toEqual({ filename: 'licences.xlsx', rowsCount: 17 })
    expect(global.fetch).toHaveBeenCalledWith('/api/federation/extract-excel/?campaignId=42', {
      headers: { Authorization: 'Bearer test-token' },
      signal: undefined,
    })
  })

  it('propage le détail de l’erreur FFCK', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ error: 'FFCK extranet unavailable' }),
    })

    await expect(importCampaignFfckExport(42)).rejects.toThrow('FFCK extranet unavailable')
  })
})
