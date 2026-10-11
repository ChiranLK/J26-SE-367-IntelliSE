import { useCallback, useEffect, useRef, useState } from 'react'
import { checkBackendHealth } from '../services/api.js'

export function useBackendStatus() {
  const [status, setStatus] = useState({ state: 'loading', detail: '' })
  const pendingRequest = useRef(null)

  const checkConnection = useCallback(() => {
    pendingRequest.current?.abort()
    const controller = new AbortController()
    pendingRequest.current = controller
    return checkBackendHealth({ signal: controller.signal })
      .then(() => {
        if (!controller.signal.aborted) setStatus({ state: 'connected', detail: '' })
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setStatus({ state: 'unavailable', detail: error.message })
        }
      })
  }, [])

  useEffect(() => {
    void checkConnection()
    return () => pendingRequest.current?.abort()
  }, [checkConnection])

  const retry = () => {
    setStatus({ state: 'loading', detail: '' })
    void checkConnection()
  }

  return { ...status, retry }
}
