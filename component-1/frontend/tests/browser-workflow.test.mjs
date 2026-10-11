/** Browser UI verification against a test-only HTTP fixture. No live LLM or MongoDB. */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'

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

async function waitUntil(action, description) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (await action()) return
    await delay(100)
  }
  throw new Error(`Timed out: ${description}`)
}

async function connectBrowser(executable, profile) {
  const process = spawn(executable, ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] })
  const address = await new Promise((resolve, reject) => {
    let stderr = ''
    const timeout = setTimeout(() => { process.kill(); reject(new Error('Browser startup timed out. Check C1_BROWSER_PATH and sandbox permissions.')) }, 10000)
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

test('project creation, pagination, extraction, recovery and refresh in a real browser with mocked API', { timeout: 60000 }, async (t) => {
  const projects = Array.from({ length: 12 }, (_, n) => ({ id: id(n + 1), name: `Fixture project ${n + 1}`, description: null, discussion_text: source, status: 'draft', created_at: date, updated_at: date }))
  let createFailure = true
  let extractionMode = 'success'
  let latestFailure = false
  let listFailure = false
  let createCalls = 0
  let extractionCalls = 0
  let latestCalls = 0
  let savedRun = null
  const pages = []
  const api = createServer(async (request, response) => {
    response.setHeader('Access-Control-Allow-Origin', '*')
    response.setHeader('Access-Control-Allow-Headers', 'Content-Type')
    response.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    if (request.method === 'OPTIONS') { response.writeHead(204).end(); return }
    function reply(status, data) { response.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(data)) }
    const url = new URL(request.url, 'http://fixture.test')
    const path = url.pathname.replace('/api/v1/component-1', '')
    if (path === '/health') { reply(200, { status: 'ok', component: 'component-1', service: 'requirement-engineering' }); return }
    if (path === '/projects' && request.method === 'GET') {
      if (listFailure) { reply(503, { detail: 'Fixture backend unavailable.' }); return }
      const limit = Number(url.searchParams.get('limit'))
      const offset = Number(url.searchParams.get('offset'))
      pages.push(offset)
      const items = projects.slice(offset, offset + limit).map((item) => {
        const summary = { ...item }
        delete summary.discussion_text
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
      const input = JSON.parse(body)
      const project = { ...input, id: id(100), name: input.name.trim(), status: 'draft', created_at: date, updated_at: date }
      projects.unshift(project)
      reply(201, project)
      return
    }
    const project = projects.find((item) => path.startsWith(`/projects/${item.id}`))
    if (!project) { reply(404, { detail: 'Project not found.' }); return }
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
      savedRun = { run_id: `fixture-run-${extractionCalls}`, project_id: project.id, source_discussion_hash: 'a'.repeat(64), created_at: date, model_identifier: 'mock-browser-model', prompt_version: 'c1-atomic-evidence-v1', candidates: extractionMode === 'empty' ? [] : [{ requirement_id: `fixture-requirement-${extractionCalls}`, requirement_text: quote, actor: 'Guests', action: 'delete', review_status: 'unreviewed', evidence: [{ quote, start, end: start + quote.length }] }] }
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
  await waitText('Guests must not delete reports.')
  assert.equal(await evaluate('document.querySelector(".requirement-text b")'), null)
  assert.equal(await evaluate('document.querySelector(".evidence blockquote b")'), null)
  await screenshot(screenshotPath.replace(/\.png$/, '-desktop.png'))
  await reload()
  await waitText('1 requirement candidate')
  assert.equal(extractionCalls, 1, 'refresh must not repeat extraction')
  assert.ok(latestCalls >= 2)
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
})
