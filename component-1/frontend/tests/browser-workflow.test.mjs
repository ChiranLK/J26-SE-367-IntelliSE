/** Browser UI verification against a test-only HTTP fixture. No live LLM or MongoDB. */
import assert from 'node:assert/strict'
import { createHash, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { transcriptionId, transcriptionJob, originalTranscript } from './transcription-fixture.js'
import { provenanceContract, projectProvenance } from './project-provenance-fixture.js'

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const date = '2026-10-12T00:00:00Z'
const id = (n) => n.toString(16).padStart(24, '0')
const quote = 'Guests must not delete reports. <b>Source stays plain text.</b> Reports should load quickly.'
const source = `Hi 👋\n${quote}`

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
  return { command, evaluate, close: async () => {
    const exited = process.exitCode !== null || process.signalCode !== null ? Promise.resolve() : once(process, 'exit')
    try { await send('Browser.close') } catch { /* Browser shutdown closes the protocol socket. */ }
    socket.close()
    process.kill()
    await Promise.race([exited, delay(5000)])
  } }
}

test('project creation, extraction, classification, recovery and refresh in a real browser with mocked API', { timeout: 60000 }, async (t) => {
  const projects = Array.from({ length: 12 }, (_, n) => ({ id: id(n + 1), name: `Fixture project ${n + 1}`, description: null, discussion_text: source, status: 'draft', created_at: date, updated_at: date }))
  let createFailure = true
  let deleteFailure = false
  let deleteCalls = 0
  let extractionMode = 'success'
  let latestFailure = false
  let listFailure = false
  let createCalls = 0
  let extractionCalls = 0
  let latestCalls = 0
  let savedRun = null
  const savedClassifications = new Map()
  let classificationCalls = 0
  let classificationFailure = false
  let classificationReads = 0
  let reviewPosts = 0
  const savedReviews = new Map()
  const srsStates = new Map()
  let srsPosts = 0
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
    response.setHeader('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
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
    if (request.method === 'DELETE' && path === `/projects/${project.id}`) {
      deleteCalls++
      await delay(150)
      if (deleteFailure) { reply(503, { detail: 'Fixture deletion unavailable.' }); return }
      projects.splice(projects.indexOf(project), 1)
      response.writeHead(204).end()
      return
    }
    if (path.startsWith(`/projects/${project.id}/srs`)) {
      let state = srsStates.get(project.id) ?? { schema_version: 'c1-srs-v1', project_id: project.id, revision: 0, versions: [] }
      if (request.method === 'GET') { reply(200, state); return }
      let raw = ''; for await (const chunk of request) raw += chunk
      const body = JSON.parse(raw)
      if (body.expected_revision !== state.revision) { reply(409, { detail: 'SRS changed. Refresh.' }); return }
      srsPosts++
      state = structuredClone(state)
      let version = state.versions.at(-1)
      if (path.endsWith('/srs')) {
        const classified = savedClassifications.get(body.extraction_run_id)
        const review = savedReviews.get(classified.classification_id)
        version = { version_id: randomUUID(), version_number: 1, parent_version_id: null,
          project_title: project.name, project_description: project.description,
          extraction_run_id: savedRun.run_id, classification_id: classified.classification_id,
          source_discussion_hash: savedRun.source_discussion_hash, created_at: date, created_by: body.reviewer_id,
          generation_method: 'reviewed-requirements-template-v1', status: 'draft', content_hash: 'a'.repeat(64), feedback: [], approval: null,
          requirements: savedRun.candidates.map(item => ({ requirement_id: item.requirement_id, text: item.requirement_text,
            original_text: item.requirement_text, label: review?.reviewed_label ?? classified.predictions.find(p => p.requirement_id === item.requirement_id).label, label_review_id: review?.review_id ?? null,
            source_text_hash: createHash('sha256').update(item.requirement_text).digest('hex'), authored_revision: false, change_reason: null })) }
        state.versions.push(version)
      } else if (path.endsWith('/accept-remaining')) {
        assert.equal(body.confirm, true)
        const decided = new Set(version.feedback.map(item => item.requirement_id))
        for (const item of version.requirements.filter(item => !decided.has(item.requirement_id))) {
          version.feedback.push({ feedback_id: randomUUID(), requirement_id: item.requirement_id, decision: 'accepted', comment: 'Explicit bulk acceptance', reviewer_id: body.reviewer_id, recorded_at: date, identity_status: 'self_reported' })
        }
      } else if (path.endsWith('/feedback')) {
        version.feedback.push({ feedback_id: randomUUID(), requirement_id: body.requirement_id, decision: body.decision,
          comment: body.comment, reviewer_id: body.reviewer_id, recorded_at: date, identity_status: 'self_reported' })
      } else if (path.endsWith('/revisions')) {
        version = { ...structuredClone(version), version_id: randomUUID(), version_number: version.version_number + 1,
          parent_version_id: version.version_id, content_hash: 'b'.repeat(64), status: 'draft', feedback: [], approval: null }
        Object.assign(version.requirements[0], { text: body.changes[0].text, label: body.changes[0].label,
          change_reason: body.changes[0].reason, authored_revision: true })
        state.versions.push(version)
      } else if (path.endsWith('/approval')) {
        version.status = 'approved'; version.approval = { reviewer_id: body.reviewer_id, approved_at: date, content_hash: version.content_hash, identity_status: 'self_reported' }
      }
      state.revision++; srsStates.set(project.id, state); reply(200, state); return
    }
    if (path.endsWith('/reviews')) {
      const classId = path.split('/classifications/')[1].split('/')[0]
      const classified = [...savedClassifications.values()].find((item) => item.classification_id === classId)
      if (!classified) { reply(404, { detail: 'Classification not found.' }); return }
      if (request.method === 'GET') {
        reply(200, { project_id: project.id, extraction_run_id: classified.extraction_run_id, classification_id: classId, reviews: savedReviews.has(classId) ? [savedReviews.get(classId)] : [] })
      } else {
        reviewPosts++
        let body = ''
        for await (const chunk of request) body += chunk
        const payload = JSON.parse(body)
        assert.deepEqual(Object.keys(payload).sort(), ['note', 'reviewed_label', 'reviewer_id', 'submission_id'])
        await delay(150)
        const candidate = savedRun.candidates.find(item => item.requirement_id === path.split('/requirements/')[1].split('/')[0])
        const review = { ...payload, review_id: randomUUID(), project_id: project.id, extraction_run_id: classified.extraction_run_id,
          classification_id: classId, requirement_id: candidate.requirement_id, original_prediction: 'FR',
          model_identifier: classified.model_identifier, model_version: classified.model_version,
          source_discussion_hash: savedRun.source_discussion_hash, requirement_text_hash: createHash('sha256').update(candidate.requirement_text).digest('hex'),
          reviewed_at: date, review_status: 'user_reviewed', reviewer_identity_status: 'self_reported' }
        savedReviews.set(classId, review)
        reply(201, review)
      }
      return
    }
    if (path.includes('/classifications')) {
      const runId = path.split('/extractions/')[1].split('/')[0]
      if (request.method === 'GET') {
        classificationReads++
        const saved = savedClassifications.get(runId)
        reply(saved ? 200 : 404, saved ?? { detail: 'No classification found for this extraction run.' })
      } else {
        classificationCalls++
        if (classificationFailure) { reply(503, { detail: 'FR/NFR classifier unavailable. Fixture unavailable.' }); return }
        await delay(200)
        const result = { classification_id: `9718a782-26cc-4608-9be8-${classificationCalls.toString(16).padStart(12, '0')}`, project_id: project.id,
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
      if (!savedRun || savedRun.project_id !== project.id) reply(404, { detail: 'No extraction found for this project.' })
      else reply(200, savedRun)
      return
    }
    if (path.endsWith('/extractions') && request.method === 'POST') {
      extractionCalls++
      await delay(200)
      if (extractionMode === 'unavailable') { reply(503, { detail: 'Fixture provider unavailable.' }); return }
      if (extractionMode === 'timeout-confirmed') { reply(504, { detail: 'Requirement extraction provider timed out. Check server performance, model load time and C1_LLM_TIMEOUT_SECONDS. No automatic retry was attempted.' }); return }
      if (extractionMode === 'malformed') { reply(201, { candidates: 'not a list' }); return }
      const quotes = extractionMode === 'table-demo' ? project.discussion_text.split('\n') : extractionMode === 'partial-ambiguity' ? [project.discussion_text.split('\n').at(-1)] : [quote]
      const candidates = extractionMode === 'empty' ? [] : quotes.map((text, index) => {
        const start = Array.from(project.discussion_text.slice(0, project.discussion_text.indexOf(text))).length
        return { requirement_id: `fixture-requirement-${extractionCalls}-${index}`, requirement_text: text, actor: null, action: null, review_status: 'unreviewed', evidence: [{ quote: text, start, end: start + Array.from(text).length }] }
      })
      savedRun = { run_id: `7318a782-26cc-4608-9be8-${extractionCalls.toString(16).padStart(12, '0')}`, project_id: project.id, source_discussion_hash: 'a'.repeat(64), created_at: date, model_identifier: 'mock-browser-model', prompt_version: 'c1-atomic-evidence-v1', candidates }
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
  let browser
  t.after(async () => { await browser?.close(); await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }) })
  browser = await connectBrowser(process.env.C1_BROWSER_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', profile)
  const { command, evaluate } = browser
  const includes = (value) => evaluate(`(document.body?.innerText ?? '').includes(${JSON.stringify(value)})`)
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
    await waitUntil(() => evaluate(`[...document.querySelectorAll('button')].some(el => (el.textContent.trim() === ${JSON.stringify(label)} || el.getAttribute('aria-label') === ${JSON.stringify(label)}) && !el.disabled)`), `enabled button: ${label}`)
    await evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(label)} || el.getAttribute('aria-label') === ${JSON.stringify(label)}); if (!button) throw Error('Missing button'); for (let parent = button.parentElement; parent; parent = parent.parentElement) { if (parent.tagName === 'DETAILS' && !parent.open) parent.querySelector('summary').click(); } button.click(); ${twice ? 'button.click();' : ''} })()`)
  }
  async function chooseLabel(index, value) {
    await waitUntil(() => evaluate(`Boolean(document.querySelectorAll('.review-label-trigger')[${index}]) && !document.querySelectorAll('.review-label-trigger')[${index}].disabled`), 'enabled review selector')
    const triggerPoint = await evaluate(`(() => { const trigger = document.querySelectorAll('.review-label-trigger')[${index}]; trigger.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = trigger.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 } })()`)
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', ...triggerPoint, button: 'left', clickCount: 1 })
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', ...triggerPoint, button: 'left', clickCount: 1 })
    await waitUntil(() => evaluate('Boolean(document.querySelector(".review-label-menu"))'), 'custom label menu')
    const optionPoint = await evaluate(`(() => { const r = document.querySelector('[role="option"][data-value="${value}"]').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 } })()`)
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', ...optionPoint, button: 'left', clickCount: 1 })
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', ...optionPoint, button: 'left', clickCount: 1 })
    await waitUntil(() => evaluate(`document.querySelectorAll('.review-label-trigger')[${index}].dataset.value === ${JSON.stringify(value)} && document.querySelectorAll('.review-label-trigger')[${index}].getAttribute('aria-expanded') === 'false'`), 'selected review label')
  }

  async function fill(name, value) {
    await evaluate(`(() => { const el = document.getElementById(${JSON.stringify(name)}); const setter = Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set; setter.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  }
  async function enterReviewer(value) {
    await evaluate(`(() => { const el = document.querySelector('[aria-label="Reviewer name or ID"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  }
  async function ensureReviewer() {
    if (!await evaluate(`document.querySelector('[aria-label="Reviewer name or ID"]')?.value.trim()`)) await enterReviewer('Browser reviewer')
  }
  await command('Page.enable')
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1000, deviceScaleFactor: 1, mobile: false })
  await command('Page.navigate', { url: `http://127.0.0.1:${vitePort}` })
  await waitText('Fixture project 1')
  await waitText('Create a project')
  assert.equal(await evaluate('document.querySelector(".connection-card")'), null, 'backend connectivity card is removed')
  assert.equal(await evaluate('document.querySelector(".requirement-tester")'), null, 'project flow has no duplicate standalone tester')
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
  await click('Save and open project')
  await waitText('Review the discussion and confirm it before saving.')
  assert.equal(createCalls, 0)
  await evaluate('document.querySelector("[name=source_review]").click()')
  await click('Save and open project', true)
  await waitText('Fixture database unavailable.')
  assert.equal(createCalls, 1)
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), source)
  createFailure = false
  await click('Save and open project', true)
  await waitText('No extraction yet.')
  assert.equal(await includes('No saved extraction exists for this project.'), false, 'one empty extraction message')
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
  await waitUntil(() => evaluate('Boolean(document.querySelector(".classification-project-detail .requirement-badge.fr"))'), 'saved classification badge')
  assert.equal(classificationCalls, 1)
  assert.equal(await evaluate('document.querySelector(".requirement-badge.fr").textContent'), 'FR')
  assert.equal(await evaluate('document.querySelector(".requirement-identity code").textContent'), savedRun.candidates[0].requirement_id)
  await waitText('Guests must not delete reports.')
  await waitText('No saved label reviews for this classification.')
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".requirement-review-table thead th")].map(el => el.textContent)'), ['ID', 'Requirement', 'Model prediction', 'Human review', 'Details'])
  await click('View details for R01')
  await waitText('Unclear points · 2 potential flags')
  await evaluate('document.querySelector(".requirement-table-details .ambiguity-hints").open = true')
  await waitText('What is the maximum acceptable response time')
  assert.equal(await evaluate('document.querySelector(".compact-requirement-text").textContent'), quote, 'ambiguity hints preserve candidate text')
  await click('Continue to export →')
  await waitText('Please provide your reviewer name or ID.')
  await waitUntil(() => evaluate('document.activeElement.getAttribute("aria-label") === "Reviewer name or ID"'), 'reviewer field focused after navigation')
  assert.equal(await evaluate('document.activeElement.getAttribute("aria-label")'), 'Reviewer name or ID')
  assert.equal(await evaluate('document.querySelector(".export-panel")'), null)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Reviewer name or ID"]').getAttribute("aria-invalid")`), 'true')
  await enterReviewer('   ')
  await evaluate('document.querySelectorAll(".flow-tracker button")[2].click()')
  await waitText('Please provide your reviewer name or ID.')
  assert.equal(await evaluate('document.querySelector(".export-panel")'), null, 'tracker cannot bypass the required reviewer')
  await enterReviewer('')
  await chooseLabel(0, 'NFR')
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".review-save-button")).cursor'), 'pointer')
  const postsBeforeMissingReviewer = reviewPosts
  await click('Save review')
  await waitText('Enter your reviewer name or ID above, then save your review.')
  assert.equal(reviewPosts, postsBeforeMissingReviewer, 'missing reviewer must not send a request')
  await waitUntil(() => evaluate('document.activeElement.getAttribute("aria-label") === "Reviewer name or ID"'), 'reviewer field focused after navigation')
  assert.equal(await evaluate('document.activeElement.getAttribute("aria-label")'), 'Reviewer name or ID')
  assert.equal(await includes('Discard edits'), false)
  await chooseLabel(0, '')
  await evaluate(`(() => {
    const el = document.querySelector('[aria-label="Reviewer name or ID"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, 'Browser reviewer');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    const note = document.querySelector('.label-review textarea');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(note, '<b>Review note</b>');
    note.dispatchEvent(new Event('input', { bubbles: true }));
  })()`)
  // The combobox must select without submitting its surrounding review form.
  await evaluate('document.querySelector(".review-label-trigger").focus()')
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowDown', code: 'ArrowDown', windowsVirtualKeyCode: 40 })
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await waitUntil(() => evaluate('document.querySelector(".review-label-trigger").dataset.value === "FR"'), 'keyboard FR selection')
  assert.equal(reviewPosts, 0, 'keyboard selection must not save automatically')
  await chooseLabel(0, 'NFR')
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowUp', code: 'ArrowUp', windowsVirtualKeyCode: 38 })
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Home', code: 'Home', windowsVirtualKeyCode: 36 })
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  assert.equal(await evaluate('document.querySelector(".review-label-trigger").dataset.value'), 'NFR', 'Escape preserves the selected value')
  assert.equal(await evaluate('document.querySelector(".review-label-menu")'), null)
  await evaluate('document.querySelector(".review-label-trigger").click()')
  await waitUntil(() => evaluate('Boolean(document.querySelector(".review-label-menu"))'), 'menu open before outside click')
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: 5, y: 5, button: 'left', clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: 5, y: 5, button: 'left', clickCount: 1 })
  await waitUntil(() => evaluate('document.querySelector(".review-label-menu") === null'), 'outside click dismissal')
  await ensureReviewer()
  await click('Continue to export →')
  await waitText('unsaved label review')
  assert.equal(await evaluate('Boolean(document.querySelector(".export-panel .primary-button"))'), false, 'unsaved edits block downloading')
  await click('← Back to label review')
  await click('Save review', true)
  await waitText('Reviewed label: NFR')
  assert.equal(reviewPosts, 1, 'double-click must save once')
  assert.equal(await evaluate('document.querySelector(".requirement-badge.fr").textContent'), 'FR', 'review preserves model prediction')
  assert.equal(await evaluate('document.querySelector(".review-note b")'), null, 'notes are safely rendered as text')
  await ensureReviewer()
  await click('Continue to export →')
  await waitText('Your requirements, ready to share')
  assert.equal(await evaluate('document.querySelector("#page-title").textContent'), 'Requirement Engineering')
  assert.equal(await evaluate('Boolean(document.querySelector(".future-tools, .foundation-label, .hero-description, .hero-detail"))'), false)
  const preview = JSON.parse(await evaluate('document.querySelector(".export-preview pre").textContent'))
  assert.deepEqual(Object.keys(preview), ['project_title', 'project_description', 'functional_requirements', 'non_functional_requirements'])
  assert.deepEqual(preview.non_functional_requirements, [quote], 'saved human correction determines the exported group')
  assert.deepEqual(preview.functional_requirements, [])
  await command('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: profile })
  await click('Download JSON')
  const jsonName = `${preview.project_title}.json`
  await waitUntil(async () => (await readdir(profile)).includes(jsonName), 'JSON download')
  assert.deepEqual(JSON.parse(await readFile(join(profile, jsonName), 'utf8')), preview)
  await evaluate('document.querySelector("input[name=export-format][value=txt]").click()')
  await waitText('Preview text export')
  await click('Download text')
  const textName = jsonName.replace(/\.json$/, '.txt')
  await waitUntil(async () => (await readdir(profile)).includes(textName), 'text download')
  const textExport = await readFile(join(profile, textName), 'utf8')
  assert.ok(textExport.includes('Non-functional requirements (NFR)') && textExport.includes(quote))
  assert.ok(!textExport.includes('Original model prediction'))
  await screenshot(screenshotPath.replace(/\.png$/, '-export.png'))
  await click('Continue to SRS →')
  await waitText('No saved SRS yet.')
  assert.equal(await evaluate('getComputedStyle(document.querySelectorAll(".flow-tracker li")[2], "::after").backgroundColor'), 'rgb(24, 119, 89)', 'connector from export to active SRS is green')
  assert.equal(await evaluate('document.querySelectorAll(".flow-tracker li")[2].classList.contains("complete")'), false, 'navigation does not claim that a file was exported')
  await click('Generate draft SRS')
  await waitText('Enter the reviewer name or ID before saving.')
  assert.equal(srsPosts, 0)
  await evaluate(`(() => { const el = document.querySelector('[aria-label="SRS reviewer name or ID"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, 'Demo client'); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await click('Generate draft SRS', true)
  await waitText('SRS v1')
  assert.equal(srsPosts, 1, 'double click creates one SRS draft')
  assert.equal(await evaluate('document.querySelector(".srs-requirement .requirement-badge").textContent'), 'NFR', 'SRS uses saved reviewed label')
  assert.equal(await evaluate('document.querySelector(".srs-requirement > p b")'), null, 'SRS text stays plain text')
  await evaluate('document.querySelector(".client-decision-picker button").click()')
  await waitUntil(() => evaluate('Boolean(document.querySelector(".review-label-menu [data-value=request_changes]"))'), 'styled decision menu open')
  await evaluate('document.querySelector(".review-label-menu [data-value=request_changes]").click()')
  await evaluate(`(() => { const el = document.querySelector('.srs-feedback textarea'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, 'Restrict access to members.'); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await click('Save client decision')
  await waitText('Client decision: request changes')
  assert.equal(await evaluate('document.querySelector(".srs-save-decision").textContent'), '✓ Saved')
  assert.equal(await evaluate('document.querySelector(".srs-save-decision").disabled'), true)
  assert.equal(await evaluate('[...document.querySelectorAll(".srs-workspace button")].find(el => el.textContent.startsWith("Approve SRS")).disabled'), true)
  await evaluate('document.querySelector(".srs-revision").open = true')
  await evaluate(`(() => { const fields = document.querySelectorAll('.srs-revision textarea'); const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; setter.call(fields[0], 'Only members shall be able to upload reports.'); fields[0].dispatchEvent(new Event('input', { bubbles: true })); setter.call(fields[1], 'Client requested permission restriction.'); fields[1].dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await click('Save new SRS version')
  await waitText('SRS v2')
  await waitText('Client decision pending')
  assert.equal(await evaluate('document.querySelector(".srs-bulk-review .primary-button").disabled'), true)
  await evaluate('document.querySelector(".srs-bulk-confirm input").click()')
  await click('Accept 1 remaining requirements', true)
  await waitText('Client decision: accepted')
  assert.equal(await evaluate('document.querySelector(".srs-save-decision").textContent'), '✓ Saved')
  await evaluate('document.querySelector(".srs-approval input").click()')
  await click('Approve SRS version 2', true)
  await waitText('Approved by Demo client')
  assert.equal(srsPosts, 5, 'draft, feedback, revision, acceptance and approval each saved once')
  await click('Download SRS JSON')
  const srsName = `${preview.project_title} SRS v2.json`
  await waitUntil(async () => (await readdir(profile)).includes(srsName), 'SRS download')
  const approvedSrs = JSON.parse(await readFile(join(profile, srsName), 'utf8'))
  assert.equal(approvedSrs.status, 'approved')
  assert.equal(approvedSrs.requirements[0].text, 'Only members shall be able to upload reports.')
  await click('Refresh saved SRS')
  await waitText('Approved by Demo client')
  await screenshot(screenshotPath.replace(/\.png$/, '-srs-review.png'))
  await evaluate('document.querySelector(".srs-version-select select").value = document.querySelector(".srs-version-select option").value; document.querySelector(".srs-version-select select").dispatchEvent(new Event("change", { bubbles: true }))')
  await waitText('Historical version — read only.')
  assert.equal(await evaluate('document.querySelector(".srs-feedback")'), null)
  await click('← Back to label review')

  assert.equal(await evaluate('document.querySelector(".requirement-text b")'), null)
  assert.equal(await evaluate('document.querySelector(".evidence blockquote b")'), null)
  await screenshot(screenshotPath.replace(/\.png$/, '-desktop.png'))
  await reload()
  await waitText('1 requirement candidate')
  assert.equal(extractionCalls, 1, 'refresh must not repeat extraction')
  assert.ok(latestCalls >= 2)
  await waitUntil(() => evaluate('Boolean(document.querySelector(".classification-project-detail .requirement-badge.fr"))'), 'retrieved classification badge')
  assert.equal(classificationCalls, 1, 'reload retrieves classification without a POST')
  assert.ok(classificationReads >= 2)
  await waitText('Reviewed label: NFR')
  assert.equal(reviewPosts, 1, 'reload retrieves review without submitting it again')
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
  await evaluate('document.querySelector(".extraction-evidence").open = true')
  await waitText('Extraction completed successfully with no requirement candidates.')
  assert.equal(extractionCalls, 4)
  await waitText('This saved extraction contains no requirements.')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-badge.fr").length'), 0, 'old classification badges cannot cross to a new run')
  assert.equal(classificationCalls, 1)
  assert.equal(await includes('Reviewed label: NFR'), false, 'old reviews cannot cross extraction runs')
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
  assert.equal(await evaluate('document.querySelector(".discussion-tabs").dataset.active'), 'audio')
  assert.equal(await evaluate('getComputedStyle(document.getElementById("audio-file")).cursor'), 'pointer')
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".audio-transcribe-button")).cursor'), 'not-allowed')
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'glass upload fits mobile')
  await screenshot(screenshotPath.replace(/\.png$/, '-glass-audio-mobile.png'))
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1000, deviceScaleFactor: 1, mobile: false })
  await screenshot(screenshotPath.replace(/\.png$/, '-glass-audio-desktop.png'))
  await evaluate('document.getElementById("source-audio-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }))')
  assert.equal(await evaluate('document.activeElement.id'), 'source-paste-tab')
  assert.equal(await evaluate('document.querySelector(".discussion-tabs").dataset.active'), 'paste')
  assert.equal(await evaluate('document.getElementById("source-audio-panel").hidden'), true)
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'Existing pasted discussion.')
  await screenshot(screenshotPath.replace(/\.png$/, '-glass-text-desktop.png'))
  await click('Upload audio')
  await command('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] })
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".discussion-tabs"), "::before").transitionDuration'), '0s')
  assert.equal(await evaluate('getComputedStyle(document.getElementById("source-audio-panel")).animationName'), 'none')
  await command('Emulation.setEmulatedMedia', { features: [] })
  await command('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 1, mobile: true })
  async function selectAudio(name = 'fixture.wav', size = 10) {
    await evaluate(`(() => { const input = document.getElementById('audio-file'); const files = new DataTransfer(); files.items.add(new File([new Uint8Array(${size})], ${JSON.stringify(name)}, { type: 'audio/wav' })); input.files = files.files; input.dispatchEvent(new Event('change', { bubbles: true })); })()`)
  }
  const enabled = (label) => evaluate(`[...document.querySelectorAll('button')].some(el => (el.textContent.trim() === ${JSON.stringify(label)} || el.getAttribute('aria-label') === ${JSON.stringify(label)}) && !el.disabled)`)
  await selectAudio('unsupported.flac')
  await waitText('Only WAV, MP3 and M4A')
  assert.equal(await enabled('Transcribe audio'), false)
  await selectAudio()
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".audio-transcribe-button")).cursor'), 'pointer')
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
  await waitText('Audio transcript linked.')
  assert.equal(await evaluate('document.querySelector(".audio-source-link").classList.contains("ready")'), true, 'linked audio uses an informational style')
  assert.equal(await evaluate('document.querySelector(".audio-source-details").open'), false, 'technical recording details start collapsed')
  assert.equal(await enabled('Save and open project'), true)
  const sourceId = transcriptionId(6)
  provenanceEnabled = false
  await evaluate('document.querySelector("[name=source_review]").click()')
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
  await click('← Review saved source')
  await waitText('Saved audio source')
  assert.equal(createCalls, 4)
  assert.equal(audioPosts, 6)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), reviewedAudioText)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source .audio-original pre").textContent'), originalTranscript)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source pre b")'), null)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source code").textContent'), sourceId)
  await reload()
  await click('← Review saved source')
  await waitText('Saved audio source')
  await click('+ New project')
  await waitText('Create a project')
  await evaluate('[...document.querySelectorAll(".project-name")].find(el => el.textContent === "Saved audio review").closest("button").click()')
  await click('← Review saved source')
  await waitText('Saved audio source')
  assert.equal(await evaluate('document.querySelector(".saved-audio-source code").textContent'), sourceId)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), reviewedAudioText)
  assert.equal(createCalls, 4, 'refresh and reopen must not repeat saving')
  assert.equal(extractionCalls, 4)
  assert.equal(classificationCalls, 1)
  // Main guided action reuses a saved extraction when classification alone fails.
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1000, deviceScaleFactor: 1, mobile: false })
  await click('+ New project')
  await waitText('Create a project')
  await fill('name', 'Guided grocery store')
  await fill('discussion_text', source)
  await evaluate('document.querySelector("[name=source_review]").click()')
  await click('Save and open project')
  await waitText('No extraction yet.')
  extractionMode = 'success'
  classificationFailure = true
  await click('Run extraction & classification', true)
  await waitText('Requirements were saved, but classification failed.')
  assert.equal(extractionCalls, 5)
  assert.equal(classificationCalls, 2)
  classificationFailure = false
  await click('Classify requirements')
  await waitText('No saved label reviews for this classification.')
  assert.equal(extractionCalls, 5)
  assert.equal(classificationCalls, 3)
  await ensureReviewer()
  await click('Continue to export →')
  await waitText('labels are still model predictions')
  const unreviewed = JSON.parse(await evaluate('document.querySelector(".export-preview pre").textContent'))
  assert.equal(unreviewed.functional_requirements.length + unreviewed.non_functional_requirements.length, 1)
  await click('← Back to label review')
  await click('Run extraction & classification', true)
  await waitUntil(() => classificationCalls === 4, 'combined action classification')
  await waitText('No saved label reviews for this classification.')
  assert.equal(extractionCalls, 6)
  assert.equal(classificationCalls, 4)
  await screenshot(screenshotPath.replace(/\.png$/, '-guided-review.png'))
  await click('Delete project Guided grocery store')
  await waitText('Delete project from dashboard?')
  await click('Cancel')
  assert.equal(deleteCalls, 0, 'cancel must not issue DELETE')
  await click('Delete project Guided grocery store')
  deleteFailure = true
  await click('Delete project', true)
  await waitText('Fixture deletion unavailable.')
  assert.equal(deleteCalls, 1, 'failure must not automatically retry')
  assert.equal(await evaluate('location.hash.startsWith("#projects/")'), true)
  deleteFailure = false
  await click('Delete project', true)
  await waitText('Create a project')
  await waitUntil(() => evaluate('![...document.querySelectorAll(".project-name")].some(el => el.textContent === "Guided grocery store")'), 'deleted project removed from dashboard')
  assert.equal(deleteCalls, 2)
  assert.ok(projects.some(project => project.name === 'Saved audio review'), 'other projects retained')
  assert.equal(await evaluate('location.hash'), '#new-project')
  await reload()
  await waitText('Create a project')
  assert.equal(await evaluate('document.body.innerText.includes("Guided grocery store")'), false)

  // Eight-row calculator fixture: layout, row identity and drafts survive detail toggles.
  const tableRequirements = [
    'Users shall be able to add two numbers.', 'Users shall be able to subtract one number from another.',
    'Users shall be able to multiply two numbers.', 'Users shall be able to divide one number by another.',
    'Users shall be able to clear the input and start a new calculation.',
    'Calculation results shall appear within one second.', 'The calculator shall operate on Windows and Linux.',
    'The calculator shall support one hundred concurrent users.',
  ]
  await fill('name', 'Calculator table preview')
  await fill('discussion_text', tableRequirements.join('\n'))
  await evaluate('document.querySelector("[name=source_review]").click()')
  await click('Save and open project')
  await waitText('No extraction yet.')
  extractionMode = 'table-demo'
  await click('Run extraction & classification')
  await waitText('No saved label reviews for this classification.')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row").length'), 8)
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".requirement-table-row .compact-requirement-text")].map(el => el.textContent)'), tableRequirements)
  await chooseLabel(0, 'FR')
  await click('View details for R02')
  await click('Hide details for R02')
  assert.equal(await evaluate('document.querySelector(".requirement-table-row .review-label-trigger").dataset.value'), 'FR', 'detail toggling must preserve unsaved selection')
  await ensureReviewer()
  await click('Continue to export →')
  await waitText('unsaved label review')
  await click('← Back to label review')
  assert.equal(await includes('Discard edits'), false)
  await chooseLabel(0, '')
  await evaluate(`(() => {
    const name = document.querySelector('[aria-label="Reviewer name or ID"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(name, 'Table reviewer'); name.dispatchEvent(new Event('input', { bubbles: true }));
  })()`)
  await chooseLabel(1, 'FR')
  const beforeTableReviews = reviewPosts
  await evaluate(`(() => { const button = document.querySelectorAll('.requirement-table-row')[1].querySelector('button.workspace-button'); button.click(); button.click(); })()`)
  await waitText('Reviewed label: FR')
  assert.equal(reviewPosts, beforeTableReviews + 1)
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row")[0].querySelector(".saved-review-details")'), null)
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row")[1].querySelector(".saved-review-details").textContent.includes("Table reviewer")'), true)
  await command('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 1, mobile: true })
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'table must not widen the page')
  assert.equal(await evaluate('document.querySelector(".requirement-table-scroll").scrollWidth > document.querySelector(".requirement-table-scroll").clientWidth'), true, 'table scroll is contained on mobile')
  await screenshot(screenshotPath.replace(/\.png$/, '-table-mobile.png'))
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await screenshot(screenshotPath.replace(/\.png$/, '-table-desktop.png'))
  await evaluate('document.querySelectorAll(".review-label-trigger")[1].focus(); document.querySelectorAll(".review-label-trigger")[1].click()')
  await waitUntil(() => evaluate('Boolean(document.querySelector(".review-label-menu"))'), 'styled dropdown screenshot')
  assert.equal(await evaluate('(() => { const r = document.querySelector(".review-label-menu").getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight })()'), true)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
  await waitUntil(() => evaluate('document.querySelector(".review-label-menu") === null'), 'Tab closes menu')
  await evaluate('document.querySelectorAll(".review-label-trigger")[1].focus(); document.querySelectorAll(".review-label-trigger")[1].click()')
  await waitUntil(() => evaluate('Boolean(document.querySelector(".review-label-menu"))'), 'menu open for viewport capture')
  const dropdownScreenshot = screenshotPath.replace(/\.png$/, '-label-dropdown.png')
  const dropdownImage = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  await writeFile(dropdownScreenshot, Buffer.from(dropdownImage.data, 'base64'))
  t.diagnostic(`Mocked dropdown viewport screenshot: ${dropdownScreenshot}`)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })

  await reload()
  await waitText('Reviewed label: FR')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row").length'), 8)
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row")[1].querySelector(".saved-review-details").textContent.includes("Table reviewer")'), true)

  await click('+ New project')
  await waitText('Create a project')
  const ambiguitySource = 'The calculator shall display results quickly.\nThe calculator shall have a user-friendly interface.\nCalculation results shall appear within one second.'
  await fill('name', 'Partial extraction ambiguity check')
  await fill('discussion_text', ambiguitySource)
  await evaluate('document.querySelector("[name=source_review]").click()')
  await click('Save and open project')
  await waitText('Unclear wording in saved discussion · 2 potential flags')
  assert.equal(await evaluate('document.querySelector(".source-ambiguity-review").open'), true)
  assert.equal(await evaluate('document.querySelectorAll(".source-ambiguity-review li").length'), 2)
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row").length'), 0, 'source review is available without extraction')
  extractionMode = 'partial-ambiguity'
  await waitText('No extraction yet.')
  await click('Run extraction & classification')
  await waitText('No saved label reviews for this classification.')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row").length'), 1, 'only actual returned requirements enter the table')
  assert.equal(await evaluate('document.querySelector(".compact-requirement-text").textContent'), 'Calculation results shall appear within one second.')
  assert.equal(await evaluate('document.querySelectorAll(".source-ambiguity-review li").length'), 2, 'omitted vague sentences remain visible as source hints')
  assert.equal(await evaluate('Boolean(document.querySelector(".requirement-review-table").compareDocumentPosition(document.querySelector(".source-ambiguity-review")) & Node.DOCUMENT_POSITION_FOLLOWING)'), true, 'source hints follow the requirement table')
  await click('View details for R01')
  await waitText('Unclear points · No rule matches')
  await ensureReviewer()
  await click('Continue to export →')
  await waitText('Your requirements, ready to share')
  const partialExport = JSON.parse(await evaluate('document.querySelector(".export-preview pre").textContent'))
  assert.deepEqual(partialExport.functional_requirements, ['Calculation results shall appear within one second.'], 'export preserves the mocked classifier label without inventing a correction')
  assert.deepEqual(partialExport.non_functional_requirements, [])
  assert.equal('source_ambiguity_analysis' in partialExport, false)
  await click('← Back to label review')
  await reload()
  await waitText('Unclear wording in saved discussion · 2 potential flags')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row").length'), 1)
  await ensureReviewer()
  await click('Continue to export →')
  await click('Continue to SRS →')
  await waitText('No saved SRS yet.')
  assert.equal(await evaluate('getComputedStyle(document.querySelectorAll(".flow-tracker li")[2], "::after").backgroundColor'), 'rgb(24, 119, 89)', 'connector from export to active SRS is green')
  assert.equal(await evaluate('document.querySelectorAll(".flow-tracker li")[2].classList.contains("complete")'), false, 'navigation does not claim that a file was exported')
  await evaluate(`(() => { const el = document.querySelector('[aria-label="SRS reviewer name or ID"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, 'Exception reviewer'); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  const reviewsBeforeDraft = reviewPosts
  await click('Generate draft SRS')
  await waitText('SRS v1')
  assert.equal(reviewPosts, reviewsBeforeDraft, 'draft generation must not fabricate human label reviews')
  assert.equal(await evaluate('document.querySelector(".srs-requirement > details").textContent.includes("Model prediction — no human label review")'), true)
  assert.equal(await evaluate('document.querySelectorAll(".srs-feedback").length'), 1)
  await evaluate('document.querySelector(".srs-bulk-confirm input").click()')
  await click('Accept 1 remaining requirements')
  await waitText('Client decision: accepted')
  assert.equal(await evaluate('document.querySelector(".srs-save-decision").textContent'), '✓ Saved')
  await command('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 1, mobile: true })
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'client decision controls fit mobile viewport')
  await screenshot(screenshotPath.replace(/\.png$/, '-srs-exception-mobile.png'))
  await click('← Back to label review')
  extractionMode = 'timeout-confirmed'
  const callsBeforeTimeout = extractionCalls
  await click('Run extraction & classification')
  await waitText('Extraction timed out before a run was saved.')
  assert.equal(await evaluate('Boolean(document.querySelector(".recovery-message"))'), false, 'confirmed backend timeout does not leave uncertain persistence lock')
  assert.equal(await evaluate('[...document.querySelectorAll("button")].find(el => el.textContent === "Run extraction & classification").disabled'), false)
  assert.equal(extractionCalls, callsBeforeTimeout + 1, 'timeout never triggers automatic retry')
  assert.equal(await evaluate('document.querySelectorAll(".requirement-table-row").length'), 1, 'saved successful run remains available')


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
  let browser
  t.after(async () => { await browser?.close(); await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }) })
  browser = await connectBrowser(process.env.C1_BROWSER_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', profile)
  const { command, evaluate } = browser
  const waitText = (text, attempts) => waitUntil(() => evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`), text, attempts)
  const click = (text) => evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(text)}); if (!button || button.disabled) throw Error('Button unavailable'); button.click() })()`)
  const fill = (id, value) => evaluate(`(() => { const el = document.getElementById(${JSON.stringify(id)}); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await command('Page.enable')
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/#new-project` })
  await waitText('Create a project')
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
  await waitText('Audio transcript linked.')
  assert.equal(await evaluate('document.getElementById("discussion_text").value'), 'A reviewed draft for this disposable UI check.')
  assert.equal(await evaluate('document.getElementById("name").value'), 'Disposable live audio review')
  assert.equal(await evaluate('document.getElementById("description").value'), 'Disposable provenance workflow verification.')
  assert.equal(await evaluate('[...document.querySelectorAll("button")].find(el => el.textContent.trim() === "Save and open project").disabled'), false)
  assert.equal(await evaluate('document.querySelector(".workspace-notice .audio-original pre").textContent.length'), metadata.characters)
  await evaluate('document.querySelector("[name=source_review]").click()')
  await click('Save and open project')
  await click('← Review saved source')
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
  await click('← Review saved source')
  await waitText('Saved audio source')
  await click('+ New project')
  await waitText('Create a project')
  await evaluate('[...document.querySelectorAll(".project-name")].find(el => el.textContent === "Disposable live audio review").closest("button").click()')
  await click('← Review saved source')
  await waitText('Saved audio source')
  assert.equal(await evaluate('location.hash.split("/")[1]'), projectId)
  assert.equal(await evaluate('document.querySelector(".saved-audio-source code").textContent'), identifier)
  assert.equal(await evaluate('document.querySelector(".discussion pre").textContent'), 'A reviewed draft for this disposable UI check.')
  assert.equal(await evaluate('document.querySelector(".connection-card")'), null)
  t.diagnostic(JSON.stringify({ check: 'actual ASR + reviewed project save + refresh + reopen', transcription_id: identifier, project_id: projectId, ...metadata }))
})

// Explicit opt-in: actual trained artifact, real Python and real browser; no model fixtures.
test('live local model: type, classify, clear stale results and classify again', { skip: process.env.C1_LIVE_MODEL_TEST !== '1', timeout: 120000 }, async (t) => {
  const reserve = createServer()
  const port = await listen(reserve)
  await new Promise((resolve) => reserve.close(resolve))
  const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port)], {
    env: { ...process.env, VITE_API_BASE_URL: 'http://127.0.0.1:1' }, stdio: 'ignore',
  })
  // SIGINT lets Vite close its HTTP server and the lazily spawned Python worker.
  t.after(() => vite.kill('SIGINT'))
  await waitUntil(async () => { try { return (await fetch(`http://127.0.0.1:${port}`)).ok } catch { return false } }, 'Vite model tester startup')
  const profile = await mkdtemp(join(tmpdir(), 'intellise-c1-live-model-'))
  let browser
  t.after(async () => { await browser?.close(); await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }) })
  browser = await connectBrowser(process.env.C1_BROWSER_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', profile)
  const { command, evaluate } = browser
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/#model-test` })
  await waitUntil(() => evaluate('Boolean(document.getElementById("test-requirement"))'), 'model tester form')
  await evaluate(`window.__modelCalls = 0; const originalFetch = window.fetch; window.fetch = (...args) => { if (String(args[0]).includes('/__local_model/classify')) window.__modelCalls++; return originalFetch(...args) }`)
  const fill = (text) => evaluate(`(() => { const input = document.getElementById('test-requirement'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, ${JSON.stringify(text)}); input.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  const click = () => evaluate(`(() => { const button = document.querySelector('.requirement-tester button[type="submit"]'); button.click(); button.click(); })()`)
  await click()
  await waitUntil(() => evaluate(`document.querySelector('.requirement-tester').innerText.includes('Enter a requirement to check.')`), 'blank input error')
  assert.equal(await evaluate('window.__modelCalls'), 0)
  for (const [index, text, expected] of [
    [1, 'The system shall allow customers to book appointments.', 'FR'],
    [2, 'Search results shall appear within two seconds.', 'NFR'],
  ]) {
    await fill(text)
    assert.equal(await evaluate(`document.querySelector('.tester-result') === null`), true)
    const started = performance.now()
    await click()
    await waitUntil(() => evaluate(`Boolean(document.querySelector('.tester-result')) || Boolean(document.querySelector('.requirement-tester [role="alert"]'))`), 'real model result', 700)
    const result = await evaluate(`(() => { const root = document.querySelector('.requirement-tester'); return { error: root.querySelector('[role="alert"]')?.textContent, label: root.querySelector('.tester-result .requirement-badge')?.textContent, text: root.querySelector('.tester-input')?.textContent, version: root.querySelector('.tester-result code')?.textContent, calls: window.__modelCalls } })()`)
    assert.equal(result.error, undefined)
    assert.equal(result.label, expected)
    assert.equal(result.text, text)
    assert.match(result.version, /^[a-f0-9]{64}$/)
    assert.equal(result.calls, index, 'duplicate clicks must produce only one request')
    t.diagnostic(`Actual saved model: ${result.label}; version ${result.version}; browser elapsed ${((performance.now() - started) / 1000).toFixed(3)} s`)
  }
  // Upload the actual downloadable sample, then run all rows against the real artifact.
  const sampleResponse = await fetch(`http://127.0.0.1:${port}/samples/fr-nfr-test.csv`)
  assert.equal(sampleResponse.status, 200)
  const sample = await sampleResponse.text()
  await evaluate(`(() => { const input = document.getElementById('requirement-csv'); const files = new DataTransfer(); files.items.add(new File([${JSON.stringify(sample)}], 'fr-nfr-test.csv', { type: 'text/csv' })); input.files = files.files; input.dispatchEvent(new Event('change', { bubbles: true })); })()`)
  await waitUntil(() => evaluate(`document.querySelectorAll('.tester-table tbody tr').length === 12`), 'sample CSV preview')
  assert.equal(await evaluate('window.__modelCalls'), 2, 'selecting a file must not classify automatically')
  const batchStarted = performance.now()
  await evaluate(`(() => { const button = [...document.querySelectorAll('.requirement-file-tester button')].find(el => el.textContent === 'Check uploaded file'); button.click(); button.click(); })()`)
  await waitUntil(() => evaluate(`document.querySelector('.requirement-file-tester').innerText.includes('File check complete: 12 requirements checked.') || Boolean(document.querySelector('.requirement-file-tester [role="alert"]'))`), 'real CSV model results', 700)
  const batch = await evaluate(`(() => { const root = document.querySelector('.requirement-file-tester'); return { error: root.querySelector('[role="alert"]')?.textContent, labels: [...root.querySelectorAll('tbody .requirement-badge')].map(el => el.textContent), comparisons: [...root.querySelectorAll('tbody tr')].map(el => el.lastElementChild.textContent), calls: window.__modelCalls } })()`)
  assert.equal(batch.error, undefined)
  assert.equal(batch.labels.length, 12)
  assert.equal(batch.calls, 14, 'each row must be classified once, without duplicate batch submission')
  assert.ok(batch.labels.every(label => /^(FR · Functional|NFR · Non-functional)$/.test(label)))
  assert.ok(batch.comparisons.every(value => ['Match', 'Mismatch'].includes(value)))
  t.diagnostic(`Actual CSV sample labels: ${JSON.stringify(batch.labels)}; comparison: ${JSON.stringify(batch.comparisons)}; batch elapsed ${((performance.now() - batchStarted) / 1000).toFixed(3)} s`)
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`), true, 'mobile layout must not overflow')
  await evaluate(`document.querySelector('.requirement-tester').scrollIntoView()`)
  const screenshot = process.env.C1_MODEL_SCREENSHOT ?? join(tmpdir(), 'intellise-c1-model-tester.png')
  const { data } = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  await writeFile(screenshot, Buffer.from(data, 'base64'))
  t.diagnostic(`Actual model tester screenshot: ${screenshot}`)
})
