import { spawn } from 'node:child_process'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadEnv } from 'vite'

export const MODEL_PATH = '/__local_model/classify'
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const backend = resolve(frontend, '../..', '.worktrees/component-1-backend/component-1/backend')
const unavailable = 'Local model unavailable. Check C1_TEST_PYTHON, C1_TEST_MODEL_DIR and the backend baseline dependencies. No fallback model was used.'

export class ModelError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

// A single reusable Python worker; independent of project, MongoDB and Ollama APIs.
export function createModelRunner({ python = resolve(backend, '.venv/bin/python'), modelDir = resolve(backend, 'research/models/dcai-v1/lr-c10'), workerPath = resolve(frontend, 'scripts/model_worker.py'), timeoutMs = 60000 } = {}) {
  let worker = null
  let pending = null
  let buffer = ''

  function stop(error = new ModelError(503, unavailable)) {
    const process = worker
    worker = null
    buffer = ''
    if (pending) { clearTimeout(pending.timer); pending.reject(error); pending = null }
    process?.kill()
  }

  function start() {
    const process = spawn(python, [workerPath, modelDir], { stdio: ['pipe', 'pipe', 'ignore'] })
    worker = process
    const failed = () => { if (worker === process) stop() }
    process.on('error', failed)
    process.on('exit', failed)
    process.stdin.on('error', failed)
    process.stdout.on('data', (chunk) => {
      if (worker !== process) return
      buffer += chunk.toString()
      if (Buffer.byteLength(buffer) > 65536) { stop(); return }
      const newline = buffer.indexOf('\n')
      if (newline < 0) return
      const line = buffer.slice(0, newline)
      buffer = buffer.slice(newline + 1)
      try {
        const data = JSON.parse(line)
        if (!pending || buffer.trim() || !data || typeof data !== 'object') { stop(); return }
        const task = pending
        pending = null
        clearTimeout(task.timer)
        if (data.error) task.reject(new ModelError(503, unavailable))
        else task.resolve(data)
      } catch { stop() }
    })
  }

  return {
    predict(text) {
      if (pending) return Promise.reject(new ModelError(429, 'The local model is busy. Wait for the current check to finish.'))
      return new Promise((resolve, reject) => {
        pending = { resolve, reject, timer: setTimeout(() => stop(new ModelError(504, 'The local model check timed out. It was not retried.')), timeoutMs) }
        if (!worker) start()
        worker.stdin.write(`${JSON.stringify({ requirement_text: text })}\n`)
      })
    },
    close: stop,
  }
}

export function modelMiddleware(runner) {
  return async (request, response, next) => {
    if (request.url?.split('?')[0] !== MODEL_PATH) { next(); return }
    function reply(status, data) {
      response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
      response.end(JSON.stringify(data))
    }
    if (request.method !== 'POST') { reply(405, { detail: 'Use POST for a local model check.' }); return }
    // Restrict this diagnostic endpoint to same-origin JSON; never enable CORS.
    if (request.headers.origin) {
      try {
        if (new URL(request.headers.origin).host !== request.headers.host) throw new Error()
      } catch { reply(403, { detail: 'Use the local frontend to check the model.' }); return }
    }
    if (request.headers['sec-fetch-site'] === 'cross-site') { reply(403, { detail: 'Use the local frontend to check the model.' }); return }
    if (request.headers['content-type']?.split(';')[0] !== 'application/json') { reply(415, { detail: 'Send a JSON requirement.' }); return }
    try {
      let bytes = 0
      const chunks = []
      for await (const chunk of request) {
        bytes += chunk.length
        if (bytes > 32768) throw new ModelError(413, 'Requirement request is too large.')
        chunks.push(chunk)
      }
      let input
      try { input = JSON.parse(Buffer.concat(chunks).toString('utf8')) } catch { throw new ModelError(422, 'Send valid JSON with requirement_text.') }
      if (!input || typeof input.requirement_text !== 'string' || !input.requirement_text.trim() || Array.from(input.requirement_text).length > 5000
        || Object.keys(input).some((key) => key !== 'requirement_text')) {
        throw new ModelError(422, 'Enter one requirement, between 1 and 5,000 characters.')
      }
      reply(200, await runner.predict(input.requirement_text))
    } catch (error) {
      reply(error instanceof ModelError ? error.status : 503, { detail: error instanceof ModelError ? error.message : unavailable })
    }
  }
}

export default function localModelPlugin() {
  let config
  return {
    name: 'component-1-local-model-tester',
    apply: 'serve',
    configResolved(resolved) { config = resolved },
    configureServer(server) {
      const env = loadEnv(config.mode, config.envDir, 'C1_TEST_')
      const runner = createModelRunner({ python: env.C1_TEST_PYTHON || undefined, modelDir: env.C1_TEST_MODEL_DIR || undefined })
      server.middlewares.use(modelMiddleware(runner))
      const close = () => runner.close()
      process.once('exit', close)
      server.httpServer?.once('close', () => {
        close()
        process.off('exit', close)
      })
    },
  }
}
