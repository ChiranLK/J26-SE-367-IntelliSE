import { readFile } from 'node:fs/promises';

const plan = JSON.parse(await readFile('/dev/stdin', 'utf8'));
const baseUrl = `http://127.0.0.1:${plan.port ?? 3001}`;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function request(path, { method = 'GET', body } = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  return { status: response.status, payload };
}

async function waitUntilReady(path) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await request(path);
      if (response.status === 200) return;
    } catch (_error) {
      // The process may still be starting. Retry only within this fixed limit.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Backend did not become ready at ${path}.`);
}

assert(Array.isArray(plan.entities) && plan.entities.length > 0, 'Smoke plan has no entities.');
await waitUntilReady(plan.entities[0].collectionPath);

const results = [];
for (const entity of plan.entities) {
  const initial = await request(entity.collectionPath);
  assert(initial.status === 200, `${entity.name}: initial GET must return 200.`);
  assert(Array.isArray(initial.payload) && initial.payload.length === 0, `${entity.name}: initial list must be empty.`);

  const missing = await request(entity.collectionPath, { method: 'POST', body: {} });
  assert(missing.status === 400, `${entity.name}: missing fields must return 400.`);
  assert(typeof missing.payload?.error?.code === 'string', `${entity.name}: 400 must have a structured error.`);

  const unknown = await request(entity.collectionPath, {
    method: 'POST',
    body: { ...entity.createPayload, unexpectedField: true },
  });
  assert(unknown.status === 400, `${entity.name}: unknown fields must return 400.`);

  const created = await request(entity.collectionPath, {
    method: 'POST',
    body: entity.createPayload,
  });
  assert(created.status === 201, `${entity.name}: POST must return 201.`);
  assert(typeof created.payload?.id === 'string', `${entity.name}: POST must return an id.`);
  for (const field of entity.expectedFields) {
    assert(Object.hasOwn(created.payload, field), `${entity.name}: POST response is missing ${field}.`);
  }

  const malformedId = await request(`${entity.collectionPath}/not-a-uuid`, {
    method: 'PATCH',
    body: entity.patchPayload,
  });
  assert(malformedId.status === 400, `${entity.name}: malformed id must return 400.`);

  const absent = await request(`${entity.collectionPath}/00000000-0000-4000-8000-000000000001`, {
    method: 'PATCH',
    body: entity.patchPayload,
  });
  assert(absent.status === 404, `${entity.name}: absent UUID must return 404.`);

  const updated = await request(`${entity.collectionPath}/${created.payload.id}`, {
    method: 'PATCH',
    body: entity.patchPayload,
  });
  assert(updated.status === 200, `${entity.name}: PATCH must return 200.`);
  for (const [field, value] of Object.entries(entity.patchPayload)) {
    assert(updated.payload[field] === value, `${entity.name}: PATCH did not update ${field}.`);
  }

  const listed = await request(entity.collectionPath);
  assert(listed.status === 200 && listed.payload.length === 1, `${entity.name}: GET must return the created record.`);

  const removed = await request(`${entity.collectionPath}/${created.payload.id}`, { method: 'DELETE' });
  assert(removed.status === 204 && removed.payload === null, `${entity.name}: DELETE must return 204.`);

  const removedAgain = await request(`${entity.collectionPath}/${created.payload.id}`, { method: 'DELETE' });
  assert(removedAgain.status === 404, `${entity.name}: repeated DELETE must return 404.`);

  const finalList = await request(entity.collectionPath);
  assert(finalList.status === 200 && finalList.payload.length === 0, `${entity.name}: final list must be empty.`);

  results.push({
    entity: entity.name,
    operations: ['GET', 'POST', 'PATCH', 'DELETE'],
    validationStatuses: [400, 404],
    status: 'PASS',
  });
}

process.stdout.write(`${JSON.stringify({ status: 'PASS', results })}\n`);

