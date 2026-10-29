import { spawn, execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { access } from 'node:fs/promises'
import { constants } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createConnection } from 'node:net'

const execute = promisify(execFile)
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const root = resolve(frontend, '../..')
const helper = resolve(frontend, 'scripts/startup_checks.py')
const sleep = (ms) => new Promise((done) => setTimeout(done, ms))

export function portNumber(value, name) {
  const port = Number(value)
  if (!/^\d+$/.test(String(value)) || !Number.isInteger(port) || port < 1024 || port > 65535) throw new Error(`${name} must be a port between 1024 and 65535.`)
  return port
}

export function localMongo(uri) {
  try {
    const url = new URL(uri)
    return url.protocol === 'mongodb:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) && (!url.port || url.port === '27017')
  } catch { return false }
}

export function requiredRoutes(schema) {
  return ['/health', '/projects', '/projects/{project_id}', '/projects/{project_id}/extractions', '/projects/{project_id}/extractions/{run_id}/classifications', '/transcriptions', '/transcriptions/{transcription_id}', '/projects/{project_id}/srs', '/projects/{project_id}/srs/accept-remaining']
    .every((path) => schema?.paths?.[`/api/v1/component-1${path}`])
    && Boolean(schema?.components?.schemas?.ProjectCreate?.properties?.transcription_id)
    && Boolean(schema?.components?.schemas?.SrsVersion?.properties?.generation_method?.enum?.includes('classified-requirements-template-v2'))
}

async function exists(path) {
  try { await access(path, constants.R_OK); return true } catch { return false }
}

async function command(file, args, options = {}) {
  try { return (await execute(file, args, { timeout: 10000, maxBuffer: 1024 * 1024, ...options })).stdout }
  catch { return null } // Never relay command exceptions/arguments that could contain secrets.
}

async function check(python, mode, args = [], env = process.env, timeout = 60000) {
  const output = await command(python, [helper, mode, ...args], { env, timeout })
  try { return JSON.parse(output) } catch { return null }
}

async function occupied(port) {
  const connect = (host) => new Promise((done) => {
    const socket = createConnection({ host, port })
    const finish = (value) => { socket.destroy(); done(value) }
    socket.setTimeout(500, () => finish(false))
    socket.once('connect', () => finish(true))
    socket.once('error', () => finish(false))
  })
  return (await Promise.all([connect('127.0.0.1'), connect('::1')])).some(Boolean)
}

async function json(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2500) })
    return response.ok ? await response.json() : null
  } catch { return null }
}

async function waitFor(test, timeout = 30000) {
  const until = Date.now() + timeout
  while (Date.now() < until) { if (await test()) return true; await sleep(500) }
  return false
}

export async function main(args = process.argv.slice(2)) {
  if (args.includes('--help')) {
    console.log('Usage: ./start-component-1 [--check]\nStarts local MongoDB (existing Docker volume), configured extraction provider, full backend and frontend.\n--check verifies prerequisites without starting services or writing database records.\nSettings: C1_BACKEND_DIR, C1_BACKEND_PYTHON, C1_BACKEND_PORT, C1_FRONTEND_PORT; existing backend .env settings are honored.\nNo installs, model downloads, automatic generation requests or replacement of occupied ports.')
    return
  }
  if (args.some((arg) => arg !== '--check')) throw new Error('Unknown option. Use --help.')
  if (Number(process.versions.node.split('.')[0]) !== 22 || Number(process.versions.node.split('.')[1]) < 12) throw new Error('Use Node.js 22.12 or newer in the 22.x series, as required by the frontend.')
  const checking = args.includes('--check')
  const backend = resolve(root, process.env.C1_BACKEND_DIR || '.worktrees/component-1-backend/component-1/backend')
  const python = resolve(backend, process.env.C1_BACKEND_PYTHON || '.venv/bin/python')
  if (!await exists(python)) throw new Error('Backend interpreter missing. Prepare the backend .venv using its README; do not activate a copied environment.')
  if (!await exists(resolve(frontend, 'node_modules/vite/bin/vite.js'))) throw new Error('Frontend dependencies missing. Run npm ci from component-1/frontend once.')
  const config = await check(python, 'config', [root, backend])
  if (!config?.env) throw new Error('Backend settings/import check failed. Use the full audio-enabled checkout and install it into its own .venv; inspect local .env configuration without sharing secrets.')
  const env = { ...process.env, ...config.env }
  const backendPort = portNumber(env.C1_BACKEND_PORT, 'C1_BACKEND_PORT')
  const frontendPort = portNumber(process.env.C1_FRONTEND_PORT || 5173, 'C1_FRONTEND_PORT')
  if (backendPort === frontendPort) throw new Error('Backend and frontend ports must differ.')
  const backendUrl = `http://127.0.0.1:${backendPort}`
  const frontendUrl = `http://127.0.0.1:${frontendPort}`
  env.C1_BACKEND_HOST = '127.0.0.1'
  env.C1_CORS_ORIGINS = JSON.stringify([...new Set([...JSON.parse(env.C1_CORS_ORIGINS), frontendUrl, `http://localhost:${frontendPort}`])])
  console.log('Component 01 — local full-stack launcher')
  for (const [name, port] of [['Backend', backendPort], ['Frontend', frontendPort]]) {
    if (await occupied(port)) throw new Error(`${name} port ${port} is already in use. Stop its old terminal with Ctrl+C, then rerun. No existing process was stopped.`)
  }
  console.log(`Extraction budget: ${env.C1_LLM_TIMEOUT_SECONDS}s; Ollama output limit: ${env.C1_OLLAMA_MAX_TOKENS} tokens. No automatic generation retries.`)
  console.log('Checking trained classifier and configured transcription provider…')
  const model = await check(python, 'classifier', [], env)
  if (!model?.ok) throw new Error('Classifier load failed. Configure C1_CLASSIFIER_MODEL_DIR and matching baseline dependencies. Nothing was retrained or substituted.')
  if (env.C1_TRANSCRIPTION_PROVIDER === 'azure') {
    const azure = await check(python, 'azure', [], env)
    if (!azure?.ok) throw new Error('Azure transcription configuration is incomplete. Run backend scripts/configure_azure_speech.py; no key or audio was sent to Azure.')
    console.log(`Classifier ready: ${model.model}; Azure Speech configured locally (credentials not yet checked with Azure).`)
  } else {
  if (!env.C1_WHISPER_PYTHON || !await exists(env.C1_WHISPER_PYTHON)) throw new Error('Whisper interpreter missing. Prepare the isolated ASR environment using docs/audio-transcription.md and set C1_WHISPER_PYTHON.')
  const asr = await check(env.C1_WHISPER_PYTHON, 'asr', [env.C1_WHISPER_MODEL_DIR, env.C1_WHISPER_MODEL], env)
  if (!asr?.ok) throw new Error('Whisper/FFmpeg check failed. Prepare the model explicitly using docs/audio-transcription.md; check C1_WHISPER_MODEL_DIR. No model was downloaded.')
  console.log(`Classifier ready: ${model.model}; Whisper ready: ${asr.model} (CPU).`)
  if (config.temporary_asr) console.log('Note: using existing temporary Whisper assets. Configure durable ASR paths before clearing /tmp.')
  }
  const children = []
  let stopping = false
  async function stop(code) {
    if (stopping) return
    stopping = true
    console.log('\nStopping only processes started by this launcher. MongoDB data/container are retained.')
    await Promise.all(children.reverse().map((child) => new Promise((done) => {
      if (child.exitCode !== null || child.signalCode !== null) { done(); return }
      const deadline = setTimeout(() => { child.kill('SIGKILL'); done() }, 10000)
      child.once('exit', () => { clearTimeout(deadline); done() })
      child.kill('SIGTERM')
    })))
    process.exit(code)
  }
  function start(name, file, arguments_, options = {}) {
    const child = spawn(file, arguments_, { stdio: 'inherit', ...options })
    children.push(child)
    child.once('error', () => { console.error(`${name} could not start.`); void stop(1) })
    child.once('exit', () => { if (!stopping) { console.error(`${name} stopped unexpectedly.`); void stop(1) } })
    return child
  }
  process.once('SIGINT', () => { void stop(0) })
  process.once('SIGTERM', () => { void stop(0) })
  try {
    let mongo = await check(python, 'ping', [], env, 10000)
    if (!mongo?.ok && !checking) {
      if (!localMongo(env.MONGODB_URI)) throw new Error('Configured MongoDB is unavailable. Check its service/access configuration. No local database fallback was used.')
      if (!await command('docker', ['info', '--format', '{{.ServerVersion}}'])) {
        if (process.platform !== 'darwin' || await command('open', ['-a', 'Docker']) === null) throw new Error('Start Docker Desktop or the Docker daemon, then rerun.')
        console.log('Waiting up to 60 seconds for Docker Desktop…')
        if (!await waitFor(async () => (await command('docker', ['info', '--format', '{{.ServerVersion}}'], { timeout: 2000 })) !== null, 60000)) throw new Error('Docker is not ready. Finish Docker Desktop setup and rerun.')
      }
      const state = await command('docker', ['inspect', '--format', '{{.State.Status}}', 'intellise-c1-mongodb'])
      if (state === null) {
        if (await command('docker', ['image', 'inspect', 'mongo:8.0']) === null) throw new Error('MongoDB image is not prepared. Explicitly run docker pull mongo:8.0 once, then rerun.')
        if (await command('docker', ['run', '--pull=never', '--name', 'intellise-c1-mongodb', '--publish', '127.0.0.1:27017:27017', '--volume', 'intellise-c1-mongodb-data:/data/db', '--detach', 'mongo:8.0'], { timeout: 60000 }) === null) throw new Error('Could not create the documented local MongoDB container. Inspect Docker; no existing container/volume was removed.')
      } else if (state.trim() !== 'running' && await command('docker', ['start', 'intellise-c1-mongodb'], { timeout: 60000 }) === null) throw new Error('Could not start the existing MongoDB container within 60 seconds. Inspect Docker without deleting its volume.')
      console.log('Waiting for real MongoDB…')
      if (!await waitFor(async () => (await check(python, 'ping', [], env, 10000))?.ok, 30000)) throw new Error('MongoDB did not pass its bounded ping. Check configuration and Docker; existing data were preserved.')
      mongo = { ok: true }
    }
    if (!mongo?.ok) throw new Error('MongoDB ping failed. A normal launch can start the documented local Docker service; --check never starts services.')
    console.log('Real MongoDB ping passed.')
    if (env.C1_LLM_PROVIDER === 'ollama') {
      const origin = env.C1_OLLAMA_BASE_URL.replace(/\/$/, '')
      let tags = await json(origin + '/api/tags')
      if (!tags && !checking) {
        const url = new URL(origin)
        if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.port && url.port !== '11434') throw new Error('Configured Ollama server is unavailable. No other provider was selected.')
        console.log('Starting local Ollama; no model download…')
        start('Ollama', 'ollama', ['serve'], { env: { ...process.env, OLLAMA_HOST: '127.0.0.1:11434' } })
        if (!await waitFor(async () => Boolean(await json(origin + '/api/tags')), 30000)) throw new Error('Ollama did not become ready. Install/start Ollama explicitly, then rerun.')
        tags = await json(origin + '/api/tags')
      }
      if (!tags?.models?.some((model) => [model.name, model.model].includes(env.C1_OLLAMA_MODEL))) throw new Error('Requested Ollama model is missing or Ollama is unavailable. Prepare the configured model explicitly with ollama pull; no generation, download or provider fallback was attempted.')
      console.log('Ollama ready; configured model is installed. Extraction quality still requires evaluation.')
    } else if (!env.C1_ANTHROPIC_API_KEY) throw new Error('Anthropic was explicitly selected but its API key is missing. Configure it locally or explicitly select C1_LLM_PROVIDER=ollama.')
    if (checking) { console.log('Preflight passed. No services or generation requests were started.'); return }
    start('Backend', python, ['-m', 'intelise_c1'], { cwd: backend, env })
    if (!await waitFor(async () => requiredRoutes(await json(backendUrl + '/openapi.json')))) throw new Error('Backend did not expose the current transcription/provenance and optional-label SRS API. Restart with the updated backend checkout/interpreter.')
    if (!await json(backendUrl + '/api/v1/component-1/projects?limit=1&offset=0')) throw new Error('Backend project storage is unavailable despite startup. Check MongoDB configuration.')
    start('Frontend', process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], {
      cwd: frontend, env: { ...process.env, VITE_API_BASE_URL: backendUrl, C1_TEST_PYTHON: python, C1_TEST_MODEL_DIR: env.C1_CLASSIFIER_MODEL_DIR },
    })
    if (!await waitFor(async () => { try { return (await fetch(frontendUrl, { signal: AbortSignal.timeout(2000) })).ok } catch { return false } })) throw new Error('Frontend did not become ready.')
    console.log(`\nReady: ${frontendUrl}\nAPI docs: ${backendUrl}/docs\nUpload audio → review → use transcript → save; extract/classify only through explicit actions.\nCtrl+C stops this launch. Existing MongoDB and previously running Ollama are retained.`)
  } catch (error) {
    console.error(`Startup stopped: ${error.message}`)
    await stop(1)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(`Startup stopped: ${error.message}`); process.exitCode = 1 })
}
