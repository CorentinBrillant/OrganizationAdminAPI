export const sourceColumns = [
  { key: 'nom', label: 'Nom' },
  { key: 'prenom', label: 'Prénom' },
  { key: 'licence', label: 'N° licence' },
  { key: 'type_certificat', label: 'Type certificat' },
  { key: 'expiration', label: 'Expiration' },
  { key: 'type_licence', label: 'Type de licence' },
]

export function mapFfckRowToSourceRow(row, index = 0) {
  const rawRow = row?.raw_row && typeof row.raw_row === 'object' ? row.raw_row : {}
  const rawNom = String(rawRow.nom || '').trim()
  const rawPrenom = String(rawRow.prenom || '').trim()
  const fullName = String(row?.nom || '').trim()
  const nameParts = !rawNom && !rawPrenom ? fullName.split(/\s+/).filter(Boolean) : []

  return {
    id: Number.isFinite(Number(row?.id)) ? Number(row.id) : `${row?.row_index || index}-${row?.licence || ''}`,
    nom: rawNom || nameParts[0] || '',
    prenom: rawPrenom || nameParts.slice(1).join(' '),
    licence: String(rawRow['code adherent'] || row?.licence || '').trim(),
    type_certificat: String(rawRow['type certificat'] || '').trim(),
    expiration: String(rawRow['date de fin certificat medical'] || '').trim(),
    type_licence: String(rawRow['type licence'] || '').trim(),
  }
}

export function formatApiDateTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
