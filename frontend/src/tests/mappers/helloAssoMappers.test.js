import { describe, expect, it } from 'vitest'

import { calculateHelloAssoKpis, mapHelloAssoItemToRow } from '../../mappers/helloAssoMappers'

describe('mapHelloAssoItemToRow', () => {
  it('utilise le payeur en repli et convertit les centimes', () => {
    expect(
      mapHelloAssoItemToRow({
        payer: { firstName: 'Léa', lastName: 'Martin', email: 'lea@example.test' },
        order: { formName: 'Adhésion 2026' },
        amount: 1250,
      }, 4),
    ).toEqual({
      id: '4',
      prenom: 'Léa',
      nom: 'Martin',
      email: 'lea@example.test',
      inscription: 'Adhésion 2026',
      montant: '12,50 €',
      valid: 'Valide',
    })
  })

  it('signale les champs requis absents', () => {
    const row = mapHelloAssoItemToRow({ user: { firstName: 'Léa' }, amount: { total: '1000' } }, 2)

    expect(row).toMatchObject({ nom: '—', email: '—', inscription: '—', montant: '10,00 €', valid: 'À corriger' })
  })
})

describe('calculateHelloAssoKpis', () => {
  it('calcule les lignes valides et les erreurs de mapping', () => {
    expect(calculateHelloAssoKpis([{ valid: 'Valide' }, { valid: 'À corriger' }, { valid: 'Valide' }])).toEqual({
      received: 3,
      valid: 2,
      errors: 1,
    })
  })
})
