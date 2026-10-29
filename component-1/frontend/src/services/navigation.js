export function projectFromHash(hash) {
  const match = /^#projects\/([^/]+)$/.exec(hash)
  return match ? match[1] : null
}

export const openProject = (id) => { window.location.hash = `projects/${id}` }
export const openNewProject = () => { window.location.hash = 'new-project' }
export const subscribeToHash = (listener) => {
  window.addEventListener('hashchange', listener)
  return () => window.removeEventListener('hashchange', listener)
}
export const getHash = () => window.location.hash

// A refresh can disconnect the browser while the POST continues. No discussion
// or credentials are stored, only a per-project uncertainty marker in this tab.
export function pendingExtraction(id, value) {
  try {
    const key = `intellise-c1-pending:${id.toLowerCase()}`
    if (value === undefined) return sessionStorage.getItem(key) === 'true'
    if (value) sessionStorage.setItem(key, 'true')
    else sessionStorage.removeItem(key)
  } catch { /* Storage may be disabled; in-page recovery still works. */ }
  return false
}
