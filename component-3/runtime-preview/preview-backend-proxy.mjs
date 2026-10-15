/**
 * Preview-only adapter; this file is not part of any generated manifest.
 * It exposes the generated loopback-only Express server to Docker port mapping
 * and permits only the two documented local preview origins.
 */
import http from "node:http";

const TARGET_HOST = "127.0.0.1";
const TARGET_PORT = Number(process.env.BACKEND_PORT ?? "3001");
const LISTEN_PORT = Number(process.env.BACKEND_ADAPTER_PORT ?? "3002");
const ALLOWED_ORIGINS = new Set([
  "http://127.0.0.1:5180",
  "http://localhost:5180",
]);

function corsHeaders(origin) {
  if (!origin || !ALLOWED_ORIGINS.has(origin)) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE",
    "Access-Control-Allow-Headers": "Content-Type",
    Vary: "Origin",
  };
}

function handleOptions(req, res) {
  const headers = corsHeaders(req.headers.origin);
  if (Object.keys(headers).length === 0) {
    res.writeHead(403).end();
    return;
  }
  res.writeHead(204, headers).end();
}

function proxyRequest(clientReq, clientRes) {
  const origin = clientReq.headers.origin;
  const upstreamHeaders = {
    ...clientReq.headers,
    host: `${TARGET_HOST}:${TARGET_PORT}`,
  };
  const upstream = http.request(
    {
      host: TARGET_HOST,
      port: TARGET_PORT,
      path: clientReq.url,
      method: clientReq.method,
      headers: upstreamHeaders,
    },
    (upstreamRes) => {
      const headers = { ...upstreamRes.headers };
      for (const key of Object.keys(headers)) {
        if (key.toLowerCase().startsWith("access-control-")) delete headers[key];
      }
      Object.assign(headers, corsHeaders(origin));
      clientRes.writeHead(upstreamRes.statusCode ?? 502, headers);
      upstreamRes.pipe(clientRes);
    },
  );
  upstream.on("error", (error) => {
    clientRes
      .writeHead(502, { "Content-Type": "text/plain" })
      .end(`Bad gateway: ${error.message}`);
  });
  clientReq.pipe(upstream);
}

http
  .createServer((req, res) => {
    if (req.method === "OPTIONS") handleOptions(req, res);
    else proxyRequest(req, res);
  })
  .listen(LISTEN_PORT, "0.0.0.0", () => {
    process.stdout.write(
      `preview adapter listening on 0.0.0.0:${LISTEN_PORT} -> ${TARGET_HOST}:${TARGET_PORT}\n`,
    );
  });
