import { describe, expect, it } from 'vitest'

import { mapFfckRowToSourceRow } from '../../mappers/ffckMappers'

describe('mapFfckRowToSourceRow', () => {
  it('privilégie les données brutes FFCK et conserve les noms séparés', () => {
    expect(mapFfckRowToSourceRow({
      id: 12,
      licence: 'fallback',
      nom: 'Jean Dupont',
      raw_row: {
        nom: 'Dupont',
        prenom: 'Jeanne',
        'code adherent': 'FFCK-1',
        'type certificat': 'Attestation',
        'date de fin certificat medical': '2027-01-01',
        'type licence': 'Compétition',
      },
    })).toEqual({
      id: 12,
      nom: 'Dupont',
      prenom: 'Jeanne',
      licence: 'FFCK-1',
      type_certificat: 'Attestation',
      expiration: '2027-01-01',
      type_licence: 'Compétition',
    })
  })

  it('découpe le nom API lorsque les colonnes brutes sont absentes', () => {
    expect(mapFfckRowToSourceRow({ id: 4, nom: 'Jean Claude Van Damme', licence: 'L-4' })).toMatchObject({
      nom: 'Jean',
      prenom: 'Claude Van Damme',
      licence: 'L-4',
    })
  })
})
