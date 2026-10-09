# Component 01 — Frontend foundation

AI-Powered Intelligent Requirement Engineering Agent for Agile Software Development.
The complete component is intended to transform client communications into
structured requirements, classify FR/NFR, identify quality issues, generate
Agile artifacts and an SRS, and support client review and targeted regeneration.

This branch contains only the frontend foundation. It does not represent
50% completion toward the proposed October 18, 2026 prototype deadline.
No extraction, classification, quality validation, RAG, LangGraph, audio
processing, SRS generation, MongoDB persistence, authentication, or deployment
is implemented. Other components and shared files are unchanged.

The companion branch is `component-1-backend`.
Both worktrees can run together using the addresses below.
No credentials or generated dependencies are included.

## Frontend setup and run on macOS

Requires Node.js 22.12+ within 22.x or 24.x, with npm. Verified with Node 22.14.0
and npm 11.6.1. From this worktree's repository root:

```zsh
cd component-1/frontend
npm ci
cp .env.example .env
npm run dev
```

Open <http://127.0.0.1:5173>. The companion backend runs at
<http://127.0.0.1:8001>, with health at
<http://127.0.0.1:8001/api/v1/component-1/health>.

The responsive React/Vite page shows the component purpose, planned capabilities,
and actual service connectivity: loading, connected, unavailable, and retry.
Requests time out after five seconds. The response must match the Component 01
service identity. Health is checked on mount and retry, not continuously polled.
There are no fabricated requirements, research results, or unimplemented controls.

## Environment configuration

The optional local `.env` contains:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8001
```

This is a public local placeholder, not a secret. Use the backend origin without
the health path. Restart Vite after changes; production values are embedded at
build time. Never place credentials in `VITE_*` variables.

## Verify and troubleshoot

From `component-1/frontend/`:

```zsh
npm run lint
npm run build
```

Run the companion backend to see **Backend connected**. Stop it and reload to see
**Backend unavailable** within five seconds; restart it and select **Retry
connection** to see loading followed by connected. To verify the backend directly:

```zsh
curl --fail --show-error http://127.0.0.1:8001/api/v1/component-1/health
```

Expected response:

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

If unavailable, check the backend process, API URL, browser console, and CORS
configuration. The backend must allow the exact frontend origin; localhost and
127.0.0.1 differ. Vite fails if port 5173 is occupied: stop the conflicting process
or change the port and update backend CORS. Use a supported Node version if npm
reports an engine mismatch. Installation needs registry access; retry network
failures after checking connectivity. `npm run preview` serves a production build
on port 4173; allow that origin in backend CORS before checking connectivity.
Stop with Ctrl+C. Never commit `.env`, credentials, `node_modules`, or `dist`.
