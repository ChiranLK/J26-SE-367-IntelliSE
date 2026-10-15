/** Browser UI verification against a test-only HTTP fixture. No live LLM or MongoDB. */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { transcriptionId, transcriptionJob, originalTranscript } from './transcription-fixture.js'
import { provenanceContract, projectProvenance } from './project-provenance-fixture.js'

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const date = '2026-10-12T00:00:00Z'
const id = (n) => n.toString(16).padStart(24, '0')
const source = 'Hi 👋\nGuests must not delete reports. <b>Source stays plain text.</b>'
const quote = 'Guests must not delete reports. <b>Source stays plain text.</b>'

async function listen(server) {
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  return server.address().port
}

async function waitUntil(action, description, attempts = 100) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (await action()) return
    await delay(100)
  }
  throw new Error(`Timed out: ${description}`)
}

async function connectBrowser(executable, profile) {
  const process = spawn(executable, ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] })
  const address = await new Promise((resolve, reject) => {
    let stderr = ''
    const timeout = setTimeout(() => { process.kill(); reject(new Error(`Browser startup timed out. Check C1_BROWSER_PATH and sandbox permissions. ${stderr.slice(-1000)}`)) }, 10000)
    process.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
      const match = /DevTools listening on (ws:\/\/\S+)/.exec(stderr)
      if (match) { clearTimeout(timeout); resolve(match[1]) }
    })
    process.once('error', (error) => { clearTimeout(timeout); reject(error) })
    process.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Browser exited with ${code}: ${stderr.slice(0, 1000)}`)) })
  })
  const socket = new WebSocket(address)
  await once(socket, 'open')
  let sequence = 0
  const pending = new Map()
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data)
    const callbacks = pending.get(message.id)
    if (callbacks) {
      pending.delete(message.id)
      if (message.error) callbacks.reject(new Error(message.error.message))
      else callbacks.resolve(message.result)
    }
  })
  socket.addEventListener('close', () => {
    for (const callbacks of pending.values()) callbacks.reject(new Error('Browser connection closed.'))
    pending.clear()
  })
  function send(method, params = {}, sessionId) {
    const requestId = ++sequence
    return new Promise((resolve, reject) => {
      pending.set(requestId, { resolve, reject })
      socket.send(JSON.stringify({ id: requestId, method, params, ...(sessionId ? { sessionId } : {}) }))
    })
  }
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' })
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true })
  const command = (method, params) => send(method, params, sessionId)
  async function evaluate(expression) {
    const { result, exceptionDetails } = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (exceptionDetails) throw new Error(exceptionDetails.text)
    return result.value
  }
  return { command, evaluate, close: () => { socket.close(); process.kill() } }
}

test('project creation, extraction, classification, recovery and refresh in a real browser with mocked API', { timeout: 60000 }, async (t) => {
  const projects = Array.from({ length: 12 }, (_, n) => ({ id: id(n + 1), name: `Fixture project ${n + 1}`, description: null, discussion_text: source, status: 'draft', created_at: date, updated_at: date }))
  let createFailure = true
  let extractionMode = 'success'
  let latestFailure = false
  let listFailure = false
  let createCalls = 0
  let extractionCalls = 0
  let latestCalls = 0
  let savedRun = null
  const savedClassifications = new Map()
  let classificationCalls = 0
  let classificationReads = 0
  let audioMode = 'success'
  let audioPosts = 0
  let audioGets = 0
  const audioJobs = new Map()
  let provenanceEnabled = false
  let audioReferenceFailure = false
  const pages = []
  const api = createServer(async (request, response) => {
    response.setHeader('Access-Control-Allow-Origin', '*')
    response.setHeader('Access-Control-Allow-Headers', 'Content-Type')
    response.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    if (request.method === 'OPTIONS') { response.writeHead(204).end(); return }
    function reply(status, data) { response.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(data)) }
    const url = new URL(request.url, 'http://fixture.test')
    const path = url.pathname.replace('/api/v1/component-1', '')
    if (path === '/openapi.json') { reply(200, provenanceEnabled ? provenanceContract : { paths: {} }); return }
    if (path === '/transcriptions' && request.method === 'POST') {
      audioPosts++
      const identifier = transcriptionId(audioPosts)
      assert.ok(request.headers['content-type'].startsWith('multipart/form-data; boundary='))
      let body = ''
      for await (const chunk of request) body += chunk.toString()
      assert.ok(body.includes('name="audio"'))
      audioJobs.set(identifier, { mode: audioMode, reads: 0 })
      await delay(200)
      reply(202, { transcription_id: identifier, status: 'queued' })
      return
    }
    if (path.startsWith('/transcriptions/')) {
      audioGets++
      const identifier = path.split('/').at(-1)
      const job = audioJobs.get(identifier)
      job.reads++
      if (job.mode === 'manual' && job.reads === 1) { reply(503, { detail: 'Fixture status read unavailable.' }); return }
      let result = transcriptionJob('completed', identifier)
      if (job.mode === 'success' && job.reads < 3) result = transcriptionJob(job.reads === 1 ? 'queued' : 'processing', identifier)
      if (job.mode === 'processing') result = transcriptionJob('processing', identifier)
      if (job.mode === 'failed') result = transcriptionJob('failed', identifier)
      if (job.mode === 'silence') result = { ...result, original_transcript: null, segments: [], outcome: 'silence_detected', asr_performed: false }
      reply(200, result)
      return
    }
    if (path === '/health') { reply(200, { status: 'ok', component: 'component-1', service: 'requirement-engineering' }); return }
    if (path === '/projects' && request.method === 'GET') {
      if (listFailure) { reply(503, { detail: 'Fixture backend unavailable.' }); return }
      const limit = Number(url.searchParams.get('limit'))
      const offset = Number(url.searchParams.get('offset'))
      pages.push(offset)
      const items = projects.slice(offset, offset + limit).map((item) => {
        const summary = { ...item }
        delete summary.discussion_text
        delete summary.transcription_provenance
        return summary
      })
      reply(200, { items, limit, offset, has_more: offset + limit < projects.length })
      return
    }
    if (path === '/projects' && request.method === 'POST') {
      createCalls++
      let body = ''
      for await (const chunk of request) body += chunk
      await delay(150)
      if (createFailure) { reply(503, { detail: 'Fixture database unavailable.' }); return }
      const { transcription_id, ...input } = JSON.parse(body)
      if (transcription_id && audioReferenceFailure) { reply(409, { detail: 'Referenced transcription must be completed before saving.' }); return }
      const stamp = transcription_id ? transcriptionJob().updated_at : date
      const project = { ...input, id: id(98 + createCalls), name: input.name.trim(), status: 'draft', created_at: stamp, updated_at: stamp }
      if (transcription_id) {
        assert.equal(provenanceEnabled, true)
        assert.ok(audioJobs.has(transcription_id))
        assert.deepEqual(Object.keys(input).sort(), ['description', 'discussion_text', 'name'])
        project.transcription_provenance = projectProvenance(input.discussion_text, transcriptionJob('completed', transcription_id), stamp)
        savedRun = null
      }
      projects.unshift(project)
      reply(201, project)
      return
    }
    const project = projects.find((item) => path.startsWith(`/projects/${item.id}`))
    if (!project) { reply(404, { detail: 'Project not found.' }); return }
    if (path.includes('/classifications')) {
      const runId = path.split('/extractions/')[1].split('/')[0]
      if (request.method === 'GET') {
        classificationReads++
        const saved = savedClassifications.get(runId)
        reply(saved ? 200 : 404, saved ?? { detail: 'No classification found for this extraction run.' })
      } else {
        classificationCalls++
        await delay(200)
        const result = { classification_id: `classification-${classificationCalls}`, project_id: project.id,
          extraction_run_id: runId, model_identifier: 'tfidf-logistic-regression', model_version: 'b'.repeat(64),
          classified_at: date, predictions: savedRun.candidates.map((candidate) => ({ requirement_id: candidate.requirement_id, label: 'FR' })) }
        savedClassifications.set(runId, result)
        reply(201, result)
      }
      return
    }
    if (path.endsWith('/extractions/latest')) {
      latestCalls++
      if (latestFailure) { reply(503, { detail: 'Fixture read failure.' }); return }
      if (!savedRun) reply(404, { detail: 'No extraction found for this project.' })
      else reply(200, savedRun)
      return
    }
    if (path.endsWith('/extractions') && request.method === 'POST') {
      extractionCalls++
      await delay(200)
      if (extractionMode === 'unavailable') { reply(503, { detail: 'Fixture provider unavailable.' }); return }
      if (extractionMode === 'malformed') { reply(201, { candidates: 'not a list' }); return }
      const start = Array.from(project.discussion_text).findIndex((_item, index, all) => all.slice(index, index + quote.length).join('') === quote)
      savedRun = { run_id: `7318a782-26cc-4608-9be8-${extractionCalls.toString(16).padStart(12, '0')}`, project_id: project.id, source_discussion_hash: 'a'.repeat(64), created_at: date, model_identifier: 'mock-browser-model', prompt_version: 'c1-atomic-evidence-v1', candidates: extractionMode === 'empty' ? [] : [{ requirement_id: `fixture-requirement-${extractionCalls}`, requirement_text: quote, actor: 'Guests', action: 'delete', review_status: 'unreviewed', evidence: [{ quote, start, end: start + quote.length }] }] }
      reply(201, savedRun)
      return
    }
    reply(200, project)
  })
  const apiPort = await listen(api)
  t.after(() => { api.closeAllConnections(); api.close() })
  const reserve = createServer()
  const vitePort = await listen(reserve)
  await new Promise((resolve) => reserve.close(resolve))
  const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(vitePort)], { env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${apiPort}` }, stdio: 'ignore' })
  t.after(() => vite.kill())
  await waitUntil(async () => { try { return (await fetch(`http://127.0.0.1:${vitePort}`)).ok } catch { return false } }, 'Vite startup')
  const profile = await mkdtemp(join(tmpdir(), 'intellise-c1-browser-'))
  t.after(() => rm(profile, { recursive: true, force: true }))
  const browser = await connectBrowser(process.env.C1_BROWSER_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', profile)
  t.after(browser.close)
  const { command, evaluate } = browser
  const includes = (value) => evaluate(`document.body.innerText.includes(${JSON.stringify(value)})`)
  const waitText = (value) => waitUntil(() => includes(value), value)
  async function reload() {
    await evaluate('window.__beforeReload = true')
    await command('Page.reload')
    await waitUntil(async () => {
      try { return await evaluate('window.__beforeReload === undefined && document.readyState === "complete"') }
      catch { return false }
    }, 'fresh document after reload')
  }
  const screenshotPath = process.env.C1_BROWSER_SCREENSHOT ?? join(tmpdir(), 'intellise-c1-workspace.png')
  async function screenshot(path) {
    const { cssContentSize } = await command('Page.getLayoutMetrics')
    const { data } = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { ...cssContentSize, scale: 1 } })
    await writeFile(path, Buffer.from(data, 'base64'))
    t.diagnostic(`Mocked UI screenshot: ${path}`)
  }
  async function click(label, twice = false) {
    await evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(label)}); if (!button) throw Error('Missing button'); button.click(); ${twice ? 'button.click();' : ''} })()`)
  }
  async function fill(name, value) {
    await evaluate(`(() => { const el = document.getElementById(${JSON.stringify(name)}); const setter = Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set; setter.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  }
  await command('Page.enable')
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1000, deviceScaleFactor: 1, mobile: false })
  await command('Page.navigate', { url: `http://127.0.0.1:${vitePort}` })
  await waitText('Fixture project 1')
  await waitText('Connected')
  assert.equal(extractionCalls, 0)
  await click('Next')
  await waitText('Page 2')
  assert.ok(pages.includes(10))
  await click('Previous')
  await waitText('Page 1')
  await click('Save and open project')
  await waitText('Enter a project name.')
  assert.equal(createCalls, 0)
  assert.equal(await evaluate('document.activeElement.id'), 'name')
  await fill('name', 'Browser fixture portal')
  await fill('description', 'A synthetic test project, not a research finding.')
  await fill('discussion_text', source)
  await click('Save and open project', true)
  await waitText('Fixture database unavailable.')
  assert.equal(createCalls, 1)
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), source)
  createFailure = false
  await click('Save and open project', true)
  await waitText('No extraction yet.')
  assert.equal(createCalls, 2)
  assert.equal(extractionCalls, 0)
  assert.equal(await evaluate('location.hash'), `#projects/${id(100)}`)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), source)
  assert.equal(await evaluate('document.querySelector(".discussion pre b")'), null)
  await click('Extract requirements', true)
  await waitText('1 requirement candidate')
  assert.equal(extractionCalls, 1)
  await waitText('No saved classification for this extraction.')
  assert.equal(classificationCalls, 0)
  await click('Classify requirements', true)
  await waitText('TF-IDF + logistic regression')
  assert.equal(classificationCalls, 1)
  assert.equal(await evaluate('document.querySelector(".requirement-badge.fr").textContent'), 'FR')
  assert.equal(await evaluate('document.querySelector(".requirement-identity code").textContent'), savedRun.candidates[0].requirement_id)
  await waitText('Guests must not delete reports.')
  assert.equal(await evaluate('document.querySelector(".requirement-text b")'), null)
  assert.equal(await evaluate('document.querySelector(".evidence blockquote b")'), null)
  await screenshot(screenshotPath.replace(/\.png$/, '-desktop.png'))
  await reload()
  await waitText('1 requirement candidate')
  assert.equal(extractionCalls, 1, 'refresh must not repeat extraction')
  assert.ok(latestCalls >= 2)
  await waitText('TF-IDF + logistic regression')
  assert.equal(classificationCalls, 1, 'reload retrieves classification without a POST')
  assert.ok(classificationReads >= 2)
  extractionMode = 'unavailable'
  await click('Extract requirements')
  await waitText('Fixture provider unavailable.')
  await waitText('1 requirement candidate')
  assert.equal(await evaluate('[...document.querySelectorAll("button")].find(el => el.textContent === "Extract requirements").disabled'), true)
  await reload()
  await waitText('A previous extraction may still be running')
  await waitText('1 requirement candidate')
  assert.equal(extractionCalls, 2, 'uncertain requests must not be retried on refresh')
  latestFailure = true
  await click('Retrieve latest saved result')
  await waitText('Fixture read failure.')
  await waitText('1 requirement candidate')
  latestFailure = false
  await click('Retrieve latest saved result')
  await waitUntil(() => evaluate('[...document.querySelectorAll("button")].some(el => el.textContent === "Extract requirements" && !el.disabled)'), 'recovery enables explicit extraction')
  extractionMode = 'malformed'
  await click('Extract requirements')
  await waitText('invalid response')
  await waitText('1 requirement candidate')
  await click('Retrieve latest saved result')
  await waitUntil(() => evaluate('[...document.querySelectorAll("button")].some(el => el.textContent === "Extract requirements" && !el.disabled)'), 'malformed response recovery')
  extractionMode = 'empty'
  await click('Extract requirements')
  await waitText('Extraction completed successfully with no requirement candidates.')
  assert.equal(extractionCalls, 4)
  await waitText('This saved extraction contains no requirements.')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-badge.fr").length'), 0, 'old classification badges cannot cross to a new run')
  assert.equal(classificationCalls, 1)
  await reload()
  await waitText('0 requirement candidates')
  assert.equal(extractionCalls, 4)
  await command('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 1, mobile: true })
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'mobile layout fits viewport')
  await screenshot(screenshotPath)
  await evaluate(`location.hash = 'projects/${id(999)}'`)
  await waitText('Project not found.')
  assert.equal(extractionCalls, 4)
  await evaluate("location.hash = 'projects/invalid-id'")
  await waitText('24 hexadecimal characters')
  listFailure = true
  await click('Refresh list')
  await waitText('Fixture backend unavailable.')
  listFailure = false
  await click('Retry project list')
  await waitText('Fixture project 1')
  projects.splice(0)
  await click('Refresh list')
  await waitText('No saved projects yet.')

  // Audio uses a mocked ASR contract; these checks are UI behavior, not ASR accuracy.
  await click('+ New project')
  await waitText('Create a project')
  await fill('name', 'Audio review project')
  await fill('description', 'Keep this description.')
  await fill('discussion_text', 'Existing pasted discussion.')
  await click('Upload audio')
  await waitText('Default limit: 10 MB')
  async function selectAudio(name = 'fixture.wav', size = 10) {
    await evaluate(`(() => { const input = document.getElementById('audio-file'); const files = new DataTransfer(); files.items.add(new File([new Uint8Array(${size})], ${JSON.stringify(name)}, { type: 'audio/wav' })); input.files = files.files; input.dispatchEvent(new Event('change', { bubbles: true })); })()`)
  }
  const enabled = (label) => evaluate(`[...document.querySelectorAll('button')].some(el => el.textContent.trim() === ${JSON.stringify(label)} && !el.disabled)`)
  await selectAudio('unsupported.flac')
  await waitText('Only WAV, MP3 and M4A')
  assert.equal(await enabled('Transcribe audio'), false)
  await selectAudio()
  await click('Transcribe audio', true)
  await waitText('Uploading audio')
  await waitText('Transcription queued.')
  await waitText('Transcription processing.')
  await waitText('Transcription completed.')
  assert.equal(audioPosts, 1, 'double click must submit only one upload')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'Existing pasted discussion.')
  assert.equal(await evaluate('document.getElementById("reviewed-transcript").value'), originalTranscript)
  assert.equal(await evaluate('document.querySelector(".audio-original pre b")'), null)
  await fill('reviewed-transcript', 'Reviewed appointment discussion.')
  await click('Refresh transcription status')
  await waitUntil(() => enabled('Refresh transcription status'), 'manual refresh completed')
  assert.equal(await evaluate('document.getElementById("reviewed-transcript").value'), 'Reviewed appointment discussion.')
  await click('Use this transcript')
  await waitText('Replace the existing discussion?')
  await click('Keep current discussion')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'Existing pasted discussion.')
  await click('Use this transcript')
  await click('Replace discussion')
  await waitText('Audio-derived project saving is unavailable.')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'Reviewed appointment discussion.')
  assert.equal(await evaluate('document.getElementById("name").value'), 'Audio review project')
  assert.equal(await evaluate('document.getElementById("description").value'), 'Keep this description.')
  assert.equal(await enabled('Save and open project'), false)
  await evaluate('document.querySelector("#create-heading").closest("section").querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))')
  assert.equal(createCalls, 2, 'audio provenance gap must block even programmatic form submission')
  assert.equal(extractionCalls, 4)
  assert.equal(classificationCalls, 1)
  assert.equal(await evaluate('document.querySelector(".workspace-notice .audio-original pre").textContent'), originalTranscript)
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'audio fits mobile viewport')
  await screenshot(screenshotPath.replace(/\.png$/, '-audio-review.png'))
  await click('Clear audio-derived discussion')
  await click('Keep audio discussion')
  assert.equal(await enabled('Save and open project'), false)
  await click('Clear audio-derived discussion')
  await click('Clear discussion and association')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), '')
  assert.equal(await enabled('Save and open project'), true)
  await click('Upload audio')
  audioMode = 'failed'
  await click('Transcribe audio')
  await waitText('Audio decode fixture failure.')
  assert.equal(await evaluate('document.getElementById("reviewed-transcript")'), null, 'failure cannot fabricate a transcript editor')
  audioMode = 'silence'
  await click('Transcribe audio')
  await waitText('Silence was detected; transcription was skipped.')
  assert.equal(await enabled('Use this transcript'), false)
  audioMode = 'manual'
  await click('Transcribe audio')
  await waitText('Fixture status read unavailable.')
  await waitText('Automatic polling has stopped.')
  const pausedReads = audioGets
  await delay(2200)
  assert.equal(audioGets, pausedReads, 'GET errors stop automatic polling')
  await click('Refresh transcription status')
  await waitText('Transcription completed.')
  const completedReads = audioGets
  await delay(2200)
  assert.equal(audioGets, completedReads, 'completed jobs do not keep polling')
  audioMode = 'processing'
  await click('Transcribe audio')
  await waitText('Transcription processing.')
  await evaluate(`location.hash = 'projects/${id(100)}'`)
  await waitText('Project not found.') // The list fixture was deliberately emptied above.
  const unmountedReads = audioGets
  await delay(2200)
  assert.equal(audioGets, unmountedReads, 'unmount cancels scheduled status checks')
  assert.equal(audioPosts, 5)
  assert.equal(createCalls, 2)
  assert.equal(extractionCalls, 4)
  assert.equal(classificationCalls, 1)

  // Upgrade/downgrade detection, reference errors, save and source retrieval.
  provenanceEnabled = true
  audioMode = 'success'
  await click('+ New project')
  await waitText('Create a project')
  await fill('name', 'Saved audio review')
  await fill('description', 'Keep audio description.')
  await fill('discussion_text', 'Confirm replacement of pasted text.')
  await click('Upload audio')
  await selectAudio()
  await click('Transcribe audio', true)
  await waitText('Transcription completed.')
  await fill('reviewed-transcript', ' \r\nOnly administrators can delete accounts. Café 👋\t ')
  // Native textareas expose LF line endings for an edited/pasted draft.
  const reviewedAudioText = await evaluate('document.getElementById("reviewed-transcript").value')
  await click('Use this transcript')
  await click('Replace discussion')
  await waitText('Audio source retained for saving.')
  assert.equal(await enabled('Save and open project'), true)
  const sourceId = transcriptionId(6)
  provenanceEnabled = false
  await click('Save and open project')
  await waitText('Audio-derived project saving is unavailable.')
  assert.equal(createCalls, 2, 'fresh preflight prevents a POST after backend downgrade')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), reviewedAudioText)
  provenanceEnabled = true
  await click('Check audio saving support')
  await waitUntil(() => enabled('Save and open project'), 'provenance support restored')
  audioReferenceFailure = true
  await click('Save and open project', true)
  await waitText('Referenced transcription must be completed before saving.')
  assert.equal(createCalls, 3)
  assert.equal(await evaluate('document.querySelector(".workspace-notice code").textContent'), sourceId)
  audioReferenceFailure = false
  await click('Save and open project', true)
  await waitText('Saved audio source')
  assert.equal(createCalls, 4)
  assert.equal(audioPosts, 6)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), reviewedAudioText)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source .audio-original pre").textContent'), originalTranscript)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source pre b")'), null)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source code").textContent'), sourceId)
  await reload()
  await waitText('Saved audio source')
  await click('+ New project')
  await waitText('Create a project')
  await evaluate('[...document.querySelectorAll(".project-name")].find(el => el.textContent === "Saved audio review").closest("button").click()')
  await waitText('Saved audio source')
  assert.equal(await evaluate('document.querySelector(".saved-audio-source code").textContent'), sourceId)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), reviewedAudioText)
  assert.equal(createCalls, 4, 'refresh and reopen must not repeat saving')
  assert.equal(extractionCalls, 4)
  assert.equal(classificationCalls, 1)
})

test('live audio upload, edited project save, refresh and reopen through the browser', {
  skip: !process.env.C1_LIVE_AUDIO_BASE_URL, timeout: 360000,
}, async (t) => {
  // Explicit opt-in only. Use an audio-enabled backend with a disposable DB.
  assert.ok(process.env.C1_LIVE_AUDIO_FILE, 'Set an absolute path to a real short English recording')
  const port = Number(process.env.C1_LIVE_UI_PORT ?? 18020)
  const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port)], {
    env: { ...process.env, VITE_API_BASE_URL: process.env.C1_LIVE_AUDIO_BASE_URL }, stdio: 'ignore',
  })
  t.after(() => vite.kill())
  await waitUntil(async () => { try { return (await fetch(`http://127.0.0.1:${port}`)).ok } catch { return false } }, 'live Vite startup')
  const profile = await mkdtemp(join(tmpdir(), 'intellise-c1-live-audio-browser-'))
  t.after(() => rm(profile, { recursive: true, force: true }))
  const browser = await connectBrowser(process.env.C1_BROWSER_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', profile)
  t.after(browser.close)
  const { command, evaluate } = browser
  const waitText = (text, attempts) => waitUntil(() => evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`), text, attempts)
  const click = (text) => evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(text)}); if (!button || button.disabled) throw Error('Button unavailable'); button.click() })()`)
  const fill = (id, value) => evaluate(`(() => { const el = document.getElementById(${JSON.stringify(id)}); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await command('Page.enable')
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/#new-project` })
  await waitText('Connected')
  await fill('name', 'Disposable live audio review')
  await fill('description', 'Disposable provenance workflow verification.')
  await fill('discussion_text', 'Existing discussion must be replaced explicitly.')
  await click('Upload audio')
  const { root } = await command('DOM.getDocument')
  const { nodeId } = await command('DOM.querySelector', { nodeId: root.nodeId, selector: '#audio-file' })
  await command('DOM.setFileInputFiles', { nodeId, files: [process.env.C1_LIVE_AUDIO_FILE] })
  await waitUntil(() => evaluate('document.getElementById("audio-file").files.length === 1'), 'real file selected')
  await click('Transcribe audio')
  await waitText('Transcription completed.', 3200)
  const identifier = await evaluate('document.querySelector(".audio-job code").textContent')
  const metadata = await evaluate(`fetch(${JSON.stringify(process.env.C1_LIVE_AUDIO_BASE_URL)} + '/api/v1/component-1/transcriptions/' + ${JSON.stringify(identifier)}).then(r => { if (!r.ok) throw Error('GET failed'); return r.json() }).then(job => ({ model: job.model, language: job.language, status: job.status, duration: job.audio_duration_seconds, processing: job.processing_seconds, characters: job.original_transcript.length, originalMatchesEditor: job.original_transcript === document.getElementById('reviewed-transcript').value, segments: job.segments.length }))`)
  assert.equal(metadata.status, 'completed')
  assert.equal(metadata.originalMatchesEditor, true)
  assert.equal(metadata.language, 'en')
  assert.ok(metadata.characters > 0)
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'Existing discussion must be replaced explicitly.')
  await fill('reviewed-transcript', 'A reviewed draft for this disposable UI check.')
  await click('Refresh transcription status')
  await waitUntil(() => evaluate('[...document.querySelectorAll("button")].some(el => el.textContent.trim() === "Refresh transcription status" && !el.disabled)'), 'live manual refresh')
  assert.equal(await evaluate('document.getElementById("reviewed-transcript").value'), 'A reviewed draft for this disposable UI check.')
  await click('Use this transcript')
  await waitText('Replace the existing discussion?')
  await click('Replace discussion')
  await waitText('Audio source retained for saving.')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'A reviewed draft for this disposable UI check.')
  assert.equal(await evaluate('document.getElementById("name").value'), 'Disposable live audio review')
  assert.equal(await evaluate('document.getElementById("description").value'), 'Disposable provenance workflow verification.')
  assert.equal(await evaluate('[...document.querySelectorAll("button")].find(el => el.textContent.trim() === "Save and open project").disabled'), false)
  assert.equal(await evaluate('document.querySelector(".workspace-notice .audio-original pre").textContent.length'), metadata.characters)
  await click('Save and open project')
  await waitText('Saved audio source')
  const projectId = await evaluate('location.hash.split("/")[1]')
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), 'A reviewed draft for this disposable UI check.')
  assert.equal(await evaluate('document.querySelector(".saved-audio-source .audio-original pre").textContent.length'), metadata.characters)
  await evaluate('window.__beforeReload = true')
  await command('Page.reload')
  await waitUntil(async () => {
    try { return await evaluate('window.__beforeReload === undefined && document.readyState === "complete"') }
    catch { return false }
  }, 'fresh live document after refresh')
  await waitText('Saved audio source')
  await click('+ New project')
  await waitText('Create a project')
  await evaluate('[...document.querySelectorAll(".project-name")].find(el => el.textContent === "Disposable live audio review").closest("button").click()')
  await waitText('Saved audio source')
  assert.equal(await evaluate('location.hash.split("/")[1]'), projectId)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source code").textContent'), identifier)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), 'A reviewed draft for this disposable UI check.')
  await click('Retry connection')
  await waitText('Connected')
  t.diagnostic(JSON.stringify({ check: 'actual ASR + reviewed project save + refresh + reopen', transcription_id: identifier, project_id: projectId, ...metadata }))
})
