'use strict';
/**
 * proxy-server.js
 * Minimal Node.js server (zero extra dependencies) for test/production environments.
 * - Proxies API calls to the FastAPI backend.
 * - Serves static files from web-build/ with SPA fallback to index.html.
 *
 * Usage: node proxy-server.js
 * Env:   PORT=3000  BACKEND_PORT=8001
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const STATIC_DIR = path.resolve(__dirname, 'web-build');
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT || '8001', 10);
const PORT = parseInt(process.env.PORT || '3000', 10);

const PROXY_PREFIXES = [
  '/analyze',
  '/fix',
  '/report',
  '/checklist',
  '/health',
  '/export',
  '/settings',
  '/chat',
  '/models',
  '/preview',
  '/webhook',
];

const API_GET_PREFIXES = ['/health', '/export', '/models', '/settings', '/preview'];

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff2':'font/woff2',
  '.woff': 'font/woff',
  '.ttf':  'font/ttf',
  '.map':  'application/json',
  '.txt':  'text/plain',
  '.webmanifest': 'application/manifest+json',
};

const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || 'http://localhost:3000,http://localhost:3001,http://localhost:8081,http://localhost:19006').split(',').map(s => s.trim());

function logAccess(req, res, startedAt) {
  const elapsedMs = Date.now() - startedAt;
  console.log(`${new Date().toISOString()} ${req.method} ${req.url} ${res.statusCode} ${elapsedMs}ms`);
}

const server = http.createServer((req, res) => {
  const startedAt = Date.now();
  res.on('finish', () => logAccess(req, res, startedAt));

  const reqPath = (req.url || '/').split('?')[0];

  // CORS headers — restricted to allowed origins
  const origin = req.headers.origin || '';
  if (ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // Proxy API calls to FastAPI backend.
  // GET requests to SPA routes like /checklist, /report, /fixer must serve the SPA.
  const isApiMethod = req.method !== 'GET' || API_GET_PREFIXES.some(
    (p) => reqPath === p || reqPath.startsWith(p + '/')
  );
  const shouldProxy = isApiMethod && PROXY_PREFIXES.some(
    (p) => reqPath === p || reqPath.startsWith(p + '/')
  );

  if (shouldProxy) {
    const options = {
      hostname: 'localhost',
      port: BACKEND_PORT,
      path: req.url,
      method: req.method,
      headers: { ...req.headers, host: `localhost:${BACKEND_PORT}` },
    };

    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
    });

    // 5-minute timeout to accommodate long LLM analysis requests
    proxyReq.setTimeout(300000, () => {
      proxyReq.destroy();
      if (!res.headersSent) {
        res.writeHead(504, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ detail: 'Backend request timed out' }));
      }
    });

    proxyReq.on('error', () => {
      if (!res.headersSent) {
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ detail: 'Backend unavailable' }));
      }
    });

    req.pipe(proxyReq);
    return;
  }

  // Serve static files from web-build/
  let filePath = path.join(STATIC_DIR, reqPath === '/' ? 'index.html' : reqPath);

  // Security: prevent directory traversal
  if (!filePath.startsWith(STATIC_DIR + path.sep) && filePath !== STATIC_DIR) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('Forbidden');
    return;
  }

  // SPA fallback — serve index.html for unknown paths (client-side routing)
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(STATIC_DIR, 'index.html');
  }

  const ext = path.extname(filePath).toLowerCase();
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
      return;
    }
    // The SPA contains a live provider/model catalog. Do not let the browser
    // keep an old bundle/index after models are removed from the catalog.
    res.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`Proxy server running on http://localhost:${PORT}`);
  console.log(`API requests proxied to http://localhost:${BACKEND_PORT}`);
});
