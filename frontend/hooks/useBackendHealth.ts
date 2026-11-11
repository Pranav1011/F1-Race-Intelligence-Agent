'use client'

import { useEffect } from 'react'
import { ConnectionStatus } from '@/stores/chat-store'

const POLL_INTERVAL_MS = 12_000
const REQUEST_TIMEOUT_MS = 5_000

/**
 * Polls the backend health endpoint and reports whether it answered. Polling
 * pauses while the tab is hidden and resumes with an immediate check when the
 * tab is shown again.
 */
export function useBackendHealth(url: string, onResult: (status: ConnectionStatus) => void) {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null
    let controller: AbortController | null = null
    let stopped = false

    const schedule = () => {
      if (stopped || document.hidden) return
      timer = setTimeout(check, POLL_INTERVAL_MS)
    }

    const check = async () => {
      timer = null
      controller?.abort()
      const current = new AbortController()
      controller = current
      const timeout = setTimeout(() => current.abort(), REQUEST_TIMEOUT_MS)
      let healthy = false
      try {
        const response = await fetch(url, { cache: 'no-store', signal: current.signal })
        healthy = response.ok
      } catch {
        healthy = false
      } finally {
        clearTimeout(timeout)
      }
      // A newer check, or unmounting, superseded this one
      if (stopped || controller !== current) return
      onResult(healthy ? 'connected' : 'disconnected')
      schedule()
    }

    const onVisibilityChange = () => {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      if (!document.hidden) check()
    }

    check()
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      controller?.abort()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [url, onResult])
}
