export function normalizedScrapeValue(value) {
  return value == null ? '' : String(value).trim()
}

export function shouldSelectScrapeField({ key, currentValue, newValue, currentCoverExists = false }) {
  const normalizedNewValue = normalizedScrapeValue(newValue)
  if (!normalizedNewValue) return false
  if (key === 'cover') return !currentCoverExists
  return normalizedNewValue !== normalizedScrapeValue(currentValue)
}
