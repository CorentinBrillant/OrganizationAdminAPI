export const sourceColumns = [
  { key: 'prenom', label: 'Prénom' },
  { key: 'nom', label: 'Nom' },
  { key: 'email', label: 'Email' },
  { key: 'inscription', label: 'Inscription choisie' },
  { key: 'montant', label: 'Montant (€)' },
]

function pickFirstString(...candidates) {
  return candidates.find((candidate) => typeof candidate === 'string' && candidate.trim())?.trim() || ''
}

function normalizeAmountToEuro(raw) {
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return Number.isInteger(raw) ? raw / 100 : raw
  }
  if (typeof raw === 'string' && raw.trim()) {
    const value = raw.trim().replace(',', '.')
    if (/^-?\d+$/.test(value)) return Number(value) / 100
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function extractAmountValue(item) {
  const raw = item?.amount
  const direct = normalizeAmountToEuro(raw)
  if (Number.isFinite(direct)) return direct
  if (raw && typeof raw === 'object') {
    for (const candidate of [raw.total, raw.totalAmount, raw.amount, raw.value]) {
      const normalized = normalizeAmountToEuro(candidate)
      if (Number.isFinite(normalized)) return normalized
    }
  }
  return null
}

export function formatEuro(value) {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(value)
}

export function formatApiDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

export function mapHelloAssoItemToRow(item, index) {
  const prenom = pickFirstString(item?.user?.firstName, item?.payer?.firstName)
  const nom = pickFirstString(item?.user?.lastName, item?.payer?.lastName)
  const email = pickFirstString(item?.user?.email, item?.payer?.email)
  const inscription = pickFirstString(item?.name, item?.order?.formName, item?.order?.formSlug)
  const valid = [prenom, nom, email, inscription].every(Boolean)

  return {
    id: String(item?.id ?? item?.order?.id ?? index),
    prenom: prenom || '—',
    nom: nom || '—',
    email: email || '—',
    inscription: inscription || '—',
    montant: formatEuro(extractAmountValue(item)),
    valid: valid ? 'Valide' : 'À corriger',
  }
}

export function calculateHelloAssoKpis(rows) {
  const received = rows.length
  const valid = rows.filter((row) => row.valid === 'Valide').length
  return { received, valid, errors: received - valid }
}
