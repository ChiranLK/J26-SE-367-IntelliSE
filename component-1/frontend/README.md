# Component 01 frontend

React/Vite foundation for IntelliSE's **AI-Powered Intelligent Requirement
Engineering Agent for Agile Software Development**, a fourth-year research
project. This page introduces Component 01 and checks backend connectivity.

## Implemented behavior

- Responsive landing page with semantic headings, a skip link, keyboard focus
  indicators, and an announced connection status.
- Automatic health request on mount, exact contract validation, a five-second
  timeout, and a retry button. Pending requests are cancelled on unmount or
  replacement; stale requests cannot update the page.
- Loading, connected, and unavailable states. The landing page remains usable
  when the backend is offline. Connectivity does not indicate database or AI
  readiness.
- Informational planned capabilities: text input, requirement extraction,
  FR/NFR classification, quality validation, Agile artifacts, and draft SRS
  generation. None is implemented or presented as an available control.

No persistence, model training, requirement processing, generated results, or
backend implementation is included.

## Exact macOS setup

Use **Node.js 22.12 or later in the 22.x series** and npm. Verified development
version: Node 22.14.0, pinned in `.nvmrc`. Install Node 22 first; if you already
use nvm, `nvm install` and `nvm use` from this directory select the pinned version.

From the repository root:

```sh
cd component-1/frontend
node --version
npm --version
npm ci
cp .env.example .env
npm run dev
```

Open <http://localhost:5173>. The port is fixed with `strictPort` so an occupied
port produces an error instead of silently changing the browser origin.
Stop with Ctrl+C. For subsequent sessions, run `npm run dev` from this directory.
Use npm consistently; `package-lock.json` is the reproducible dependency lockfile.

## Environment and separate backend

The example config contains:

```dotenv
VITE_API_BASE_URL=http://localhost:8001
```

Copy it to `.env` and restart Vite after editing. It should be an HTTP(S) base
URL without a query, fragment, or embedded credentials. A trailing slash is
supported. The frontend appends `/api/v1/component-1/health`.

**Every `VITE_*` value is public** and is bundled into browser code. Never put
API keys, passwords, tokens, or other credentials in these variables. Local
environment files are ignored; only `.env.example` is intended for version control.
Production configuration is selected at build time; changing `.env` requires
a new build.

The backend runs separately in another terminal. Follow the backend's own
README when its implementation is available; installing or running this
frontend does not start it. This branch does not provide a backend source implementation.
The service must allow the frontend's browser origin through CORS:
`http://localhost:5173` for development. If you use production preview, configure
`http://localhost:4173` as an allowed backend origin as well.

Expected contract:

```text
GET http://localhost:8001/api/v1/component-1/health
```

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

Only a successful HTTP response containing all three expected field values
displays **Connected**. Extra response fields are ignored. HTTP failures,
invalid JSON, mismatched contracts, network/CORS failures, and timeouts display
**Unavailable** with a short explanation. Retry performs a new request; it
is temporarily inactive during a check. No continuous polling is performed.

## Verification commands

```sh
npm run lint
npm test
npm run build
npm run preview
```

Production preview: <http://localhost:4173>. Preview is for local inspection,
not a production hosting service. The generated `dist/` directory is ignored.

The Node tests verify request routing, health validation, HTTP and network
failures, invalid JSON, timeout, cancellation, and configuration errors. They
use test-only HTTP fixtures; these are not research outputs or live integration
evidence.

For manual checks:

1. With the backend stopped, load the page. It should finish checking and show
   Unavailable while all introductory and planned-capability content remains readable.
2. Tab through the skip link and retry button. Focus should be visible. Press
   Enter or Space on retry; checking should be announced, then resolve.
3. Inspect at mobile (320–390 px), tablet, and desktop widths, and at 200% zoom.
   Content should reflow without horizontal scrolling or hidden controls.
4. When a real backend is available, start it separately and press retry. Verify
   Connected only after the actual health request succeeds. A curl response
   alone does not verify browser CORS.

## Troubleshooting

- **Unsupported Node version:** Check `node --version`; use the supported 22.x
  version and repeat `npm ci`. Do not change the lockfile to bypass an engine error.
- **Dependency download fails:** Check npm registry access and retry `npm ci`.
- **Port 5173 already in use:** Stop the other process before running Vite.
  If deliberately changing ports, update the backend's allowed CORS origins.
- **Backend unavailable:** Confirm the separate backend is running and the
  configured host/port are correct. Retry after fixing the service or network.
- **CORS failure:** Check the browser console and the backend's allowed origin.
  `localhost` and `127.0.0.1`, and different ports, are distinct origins.
- **Invalid response:** Confirm the URL reaches Component 01's health endpoint,
  not a proxy error page or another component. Check the three contract fields.
- **Request timeout:** The request is cancelled after five seconds. Check the
  backend logs and network, then retry.
- **Changed environment has no effect:** Restart the development server or
  rebuild for production. An HTTPS frontend needs an HTTPS backend to avoid
  browser mixed-content blocking.
