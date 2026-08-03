function normalize(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

export function parseFfckBirthDate(value) {
  const text = String(value || '').trim()
  if (!text) return null

  const dateParts = text.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/)
  const frenchDateParts = text.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/)
  const parts = dateParts || frenchDateParts
  if (parts) {
    const [year, month, day] = dateParts
      ? [parts[1], parts[2], parts[3]]
      : [parts[3], parts[2], parts[1]]
    const date = new Date(Number(year), Number(month) - 1, Number(day))
    if (
      date.getFullYear() === Number(year) &&
      date.getMonth() === Number(month) - 1 &&
      date.getDate() === Number(day)
    ) {
      return date
    }
  }

  if (/^\d+(?:\.0+)?$/.test(text)) {
    const serial = Number(text)
    if (serial > 0 && serial < 100000) {
      const excelDate = new Date(Date.UTC(1899, 11, 30) + serial * 86400000)
      return new Date(
        excelDate.getUTCFullYear(),
        excelDate.getUTCMonth(),
        excelDate.getUTCDate(),
      )
    }
  }

  return null
}

function isAdult(birthDate) {
  if (!birthDate) return false
  const today = new Date()
  const eighteenthBirthday = new Date(
    birthDate.getFullYear() + 18,
    birthDate.getMonth(),
    birthDate.getDate(),
  )
  return today >= eighteenthBirthday
}

function hasMissingCertificate(row) {
  return !row.certificat_file_uploaded && !String(row.certificat || '').trim()
}

function hasMissingParentalAuthorization(row) {
  return (
    row.is_minor &&
    !String(row.autorisation_parentale || '').trim() &&
    !row.autorisation_parentale_file_uploaded
  )
}

export function memberCompliance(member, ffckRow) {
  const birthDate = parseFfckBirthDate(ffckRow?.raw_row?.ddn)
  const isMajor = isAdult(birthDate)
  const row = {
    certificat: member?.certificat || '',
    certificat_file_uploaded: Boolean(member?.certificat_file?.uploaded),
    autorisation_parentale: isMajor ? 'NA' : member?.autorisation_parentale || '',
    autorisation_parentale_file_uploaded: Boolean(member?.autorisation_parentale_file?.uploaded),
    is_minor: Boolean(birthDate) && !isMajor,
    ffck_licence: member?.ffck_licence || '',
    manual_review: member?.manual_review ? 'vérifié' : 'non vérifié',
    ffck_certificat_expiration: member?.ffck_certificat_expiration || '',
    helloasso_form_slug: member?.helloasso_form_slug || '',
    ffck_licence_type: member?.ffck_licence_type || '',
  }
  const reasons = []

  if (hasMissingCertificate(row)) reasons.push('Certificat manquant')
  if (hasMissingParentalAuthorization(row)) reasons.push('Autorisation parentale manquante')

  const expiration = new Date(row.ffck_certificat_expiration)
  if (
    row.manual_review !== 'vérifié' &&
    !Number.isNaN(expiration.getTime()) &&
    expiration.getFullYear() === new Date().getFullYear()
  ) {
    reasons.push('Expiration certificat')
  }

  const formSlug = normalize(row.helloasso_form_slug)
  const licenceType = normalize(row.ffck_licence_type)
  if (
    row.manual_review !== 'vérifié' &&
    ((formSlug.includes('loisir') && licenceType.includes('competition')) ||
      (formSlug.includes('competition') && licenceType.includes('loisir')))
  ) {
    reasons.push('Incohérence entre formulaire HelloAsso et type de licence FFCK')
  }

  if (row.manual_review !== 'vérifié' && reasons.length === 0) {
    reasons.push('Vérification manuelle requise')
  }

  let status = 'Conforme'
  if (hasMissingParentalAuthorization(row) || (hasMissingCertificate(row) && !row.ffck_licence)) {
    status = 'Bloquant'
  } else if (reasons.length > 0) {
    status = 'À vérifier'
  }

  return { status, reasons }
}
