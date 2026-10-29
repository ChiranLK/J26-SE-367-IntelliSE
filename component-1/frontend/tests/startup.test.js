import assert from 'node:assert/strict'
import { test } from 'node:test'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import { localMongo, portNumber, requiredRoutes } from '../scripts/start-component-1.mjs'

test('launcher validates ports rather than coercing malformed or privileged values', () => {
  assert.equal(portNumber('8001', 'Backend'), 8001)
  for (const value of ['8001oops', '', '-1', '80', '70000', '2.5']) assert.throws(() => portNumber(value, 'Backend'))
})

test('only the documented local MongoDB target is eligible for Docker startup', () => {
  for (const uri of ['mongodb://127.0.0.1:27017', 'mongodb://localhost', 'mongodb://[::1]:27017']) assert.equal(localMongo(uri), true)
  for (const uri of ['mongodb+srv://example.invalid', 'mongodb://example.invalid:27017', 'mongodb://localhost:27018', 'not-a-uri']) assert.equal(localMongo(uri), false)
})

test('readiness rejects older project-only API and missing provenance contract', () => {
  const paths = Object.fromEntries(['/health', '/projects', '/projects/{project_id}', '/projects/{project_id}/extractions', '/projects/{project_id}/extractions/{run_id}/classifications', '/transcriptions', '/transcriptions/{transcription_id}', '/projects/{project_id}/srs', '/projects/{project_id}/srs/accept-remaining'].map(path => [`/api/v1/component-1${path}`, {}]))
  const schema = { paths, components: { schemas: { ProjectCreate: { properties: { transcription_id: {} } }, SrsVersion: { properties: { generation_method: { enum: ['reviewed-requirements-template-v1', 'classified-requirements-template-v2'] } } } } } }
  assert.equal(requiredRoutes(schema), true)
  assert.equal(requiredRoutes({ paths: { '/api/v1/component-1/projects': {} } }), false)
  assert.equal(requiredRoutes({ paths }), false)
  const legacySrs = structuredClone(schema)
  legacySrs.components.schemas.SrsVersion.properties.generation_method = { const: 'reviewed-requirements-template-v1' }
  assert.equal(requiredRoutes(legacySrs), false, 'old all-label-reviews SRS policy is not ready')
  const noBulk = structuredClone(schema)
  delete noBulk.paths['/api/v1/component-1/projects/{project_id}/srs/accept-remaining']
  assert.equal(requiredRoutes(noBulk), false)
  delete paths['/api/v1/component-1/transcriptions']
  assert.equal(requiredRoutes(schema), false)
})

test('one-command wrapper resolves its checkout even when run from another directory', async () => {
  const { stdout } = await promisify(execFile)(fileURLToPath(new URL('../../../start-component-1', import.meta.url)), ['--help'], { cwd: '/private/tmp' })
  assert.match(stdout, /Usage: .\/start-component-1/)
  assert.match(stdout, /No installs, model downloads/)
})
