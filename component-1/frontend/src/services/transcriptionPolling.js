import { ApiError, getTranscription } from './api.js'
import { terminalTranscription } from './transcriptionContracts.js'

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const cancel = () => { clearTimeout(timer); reject(signal.reason) }
    const timer = setTimeout(() => { signal?.removeEventListener('abort', cancel); resolve() }, ms)
    if (signal?.aborted) cancel()
    else signal?.addEventListener('abort', cancel, { once: true })
  })
}

export async function pollTranscription(id, { signal, onUpdate, intervalMs = 2000, maxPolls = 150, maxElapsedMs = 300000 } = {}) {
  const deadline = Date.now() + maxElapsedMs
  for (let attempt = 0; attempt < maxPolls && Date.now() < deadline; attempt++) {
    signal?.throwIfAborted()
    const job = await getTranscription(id, { signal, timeoutMs: Math.max(1, Math.min(15000, deadline - Date.now())) })
    signal?.throwIfAborted()
    onUpdate?.(job)
    if (terminalTranscription(job)) return job
    if (attempt + 1 < maxPolls && Date.now() < deadline) await delay(Math.min(intervalMs, deadline - Date.now()), signal)
  }
  throw new ApiError('Automatic status checks paused after their limit. The job may still be running; refresh its status manually.', { code: 'polling-paused' })
}
