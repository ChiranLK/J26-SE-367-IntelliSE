import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getTranscription, transcribeAudio } from '../src/services/api.js'
import { pollTranscription } from '../src/services/transcriptionPolling.js'
import { validateAudioFile, validTranscription } from '../src/services/transcriptionContracts.js'
import { transcriptionId, transcriptionJob } from './transcription-fixture.js'

test('uploads the actual file as multipart audio without a JSON Content-Type', async (t) => {
  const file = new File(['fixture bytes'], 'meeting.M4A', { type: 'audio/mp4' })
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.href, 'http://localhost:8001/api/v1/component-1/transcriptions')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers['Content-Type'], undefined)
    assert.ok(options.body instanceof FormData)
    assert.equal(options.body.get('audio').name, file.name)
    assert.equal(await options.body.get('audio').text(), 'fixture bytes')
    assert.equal(options.credentials, 'omit')
    return Response.json({ transcription_id: transcriptionId(), status: 'queued' }, { status: 202 })
  })
  assert.equal((await transcribeAudio(file)).status, 'queued')
})

test('validates extension and bytes before upload; duration remains a server check', () => {
  for (const name of ['a.wav', 'a.MP3', 'a.m4a']) assert.equal(validateAudioFile({ name, size: 10000000 }), null)
  for (const value of [null, { name: 'a.flac', size: 1 }, { name: 'a.wav', size: 0 }, { name: 'a.mp3', size: 10000001 }]) {
    assert.equal(typeof validateAudioFile(value), 'string')
  }
})

test('retrieves only a matching validated job using the centralized base URL', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url.href, `http://localhost:8001/service/api/v1/component-1/transcriptions/${transcriptionId()}`)
    return Response.json(transcriptionJob())
  })
  assert.deepEqual(await getTranscription(transcriptionId(), { baseUrl: 'http://localhost:8001/service/' }), transcriptionJob())
})

test('rejects an invalid job ID without network access', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => { throw new Error('Must not fetch') })
  assert.throws(() => getTranscription('../private'), /Invalid transcription/)
  assert.equal(mock.mock.callCount(), 0)
})

test('rejects malformed contracts and cross-job results', async (t) => {
  const job = transcriptionJob()
  for (const value of [null, {}, { ...job, transcription_id: transcriptionId(2) }, { ...job, language: 'es' },
    { ...job, segments: [{ start: 2, end: 1, text: 'bad' }] }, { ...job, processing_seconds: -1 },
    { ...job, review_status: 'approved' }, { ...job, original_transcript: null }, { ...job, segments: 'bad' }]) {
    const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(value))
    await assert.rejects(getTranscription(transcriptionId()), /invalid response/)
    mock.mock.restore()
  }
})

test('accepts queued/processing/failed and reviewable silence/empty speech outcomes', () => {
  for (const status of ['queued', 'processing', 'failed', 'completed']) assert.equal(validTranscription(transcriptionJob(status), transcriptionId()), true)
  const silent = { ...transcriptionJob(), original_transcript: null, segments: [], outcome: 'silence_detected', asr_performed: false }
  assert.equal(validTranscription(silent, transcriptionId()), true)
  assert.equal(validTranscription({ ...silent, original_transcript: 'fabricated' }, transcriptionId()), false)
  assert.equal(validTranscription({ ...transcriptionJob(), original_transcript: '', segments: [], outcome: 'no_intelligible_speech' }, transcriptionId()), true)
})

test('does not retry failed/uncertain POSTs', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Missing model.' }, { status: 503 }))
  await assert.rejects(transcribeAudio(new File(['x'], 'a.wav')), (error) => error.status === 503 && error.uncertain)
  assert.equal(mock.mock.callCount(), 1)
})

test('polls queued then processing then completed and stops', async (t) => {
  const states = ['queued', 'processing', 'completed']
  const seen = []
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(transcriptionJob(states.shift())))
  const result = await pollTranscription(transcriptionId(), { intervalMs: 1, onUpdate: (job) => seen.push(job.status) })
  assert.equal(result.status, 'completed')
  assert.deepEqual(seen, ['queued', 'processing', 'completed'])
  assert.equal(mock.mock.callCount(), 3)
})

test('polling stops on terminal failure without inventing a transcript', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(transcriptionJob('failed')))
  const job = await pollTranscription(transcriptionId(), { intervalMs: 1 })
  assert.equal(job.original_transcript, null)
  assert.equal(mock.mock.callCount(), 1)
})

test('polling is bounded by request count', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(transcriptionJob('processing')))
  await assert.rejects(pollTranscription(transcriptionId(), { intervalMs: 1, maxPolls: 2 }), (error) => error.code === 'polling-paused')
  assert.equal(mock.mock.callCount(), 2)
})

test('polling is bounded by elapsed time', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(transcriptionJob('processing')))
  await assert.rejects(pollTranscription(transcriptionId(), { intervalMs: 50, maxElapsedMs: 8 }), /refresh its status manually/)
  assert.ok(mock.mock.callCount() <= 2)
})

test('a GET error pauses polling; a separate manual GET can recover', async (t) => {
  let ready = false
  const mock = t.mock.method(globalThis, 'fetch', async () => ready ? Response.json(transcriptionJob()) : Response.json({ detail: 'DB unavailable.' }, { status: 503 }))
  await assert.rejects(pollTranscription(transcriptionId(), { intervalMs: 1 }), /DB unavailable/)
  assert.equal(mock.mock.callCount(), 1)
  ready = true
  assert.equal((await getTranscription(transcriptionId())).status, 'completed')
})

test('cleanup aborts an outstanding request and cancels future polls', async (t) => {
  const controller = new AbortController()
  const mock = t.mock.method(globalThis, 'fetch', (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  }))
  const pending = pollTranscription(transcriptionId(), { signal: controller.signal })
  controller.abort()
  await assert.rejects(pending, { name: 'AbortError' })
  assert.equal(mock.mock.callCount(), 1)
})

test('cleanup during the polling delay prevents another request', async (t) => {
  const controller = new AbortController()
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(transcriptionJob('processing')))
  const pending = pollTranscription(transcriptionId(), { signal: controller.signal, intervalMs: 1000,
    onUpdate: () => setTimeout(() => controller.abort(), 1) })
  await assert.rejects(pending, { name: 'AbortError' })
  assert.equal(mock.mock.callCount(), 1)
})
