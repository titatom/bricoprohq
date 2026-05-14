const API_URL = process.env.API_URL || 'http://api:8000';

export const config = {
  api: {
    bodyParser: false,
  },
};

const HOP_BY_HOP_HEADERS = new Set([
  'accept-encoding',
  'connection',
  'content-encoding',
  'content-length',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);
const FORWARDED_REQUEST_HEADERS = new Set([
  'accept',
  'authorization',
  'content-type',
  'user-agent',
]);

// Errors that usually mean "API container isn't ready yet" rather than a real
// failure. We retry a few times with a small backoff so the first page load
// after `docker compose up` doesn't blow up while uvicorn is still booting.
const TRANSIENT_NETWORK_CODES = new Set([
  'ECONNREFUSED',
  'ENOTFOUND',
  'EAI_AGAIN',
  'ECONNRESET',
  'ETIMEDOUT',
  'UND_ERR_SOCKET',
  'UND_ERR_CONNECT_TIMEOUT',
]);

const MAX_PROXY_ATTEMPTS = 5;
const PROXY_RETRY_DELAY_MS = 500;
const MAX_PROXY_BODY_BYTES = Number(process.env.API_PROXY_MAX_BODY_BYTES || 10 * 1024 * 1024);

function buildTargetUrl(req) {
  const apiPath = req.url.replace(/^\/api(?=\/|$)/, '') || '/';
  if (apiPath.startsWith('//')) {
    throw Object.assign(new Error('Invalid API path'), { statusCode: 400 });
  }

  const baseUrl = new URL(API_URL.endsWith('/') ? API_URL : `${API_URL}/`);
  const targetUrl = new URL(apiPath, baseUrl);
  if (targetUrl.origin !== baseUrl.origin) {
    throw Object.assign(new Error('Invalid API target'), { statusCode: 400 });
  }
  return targetUrl;
}

function copyRequestHeaders(req) {
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (
      FORWARDED_REQUEST_HEADERS.has(name.toLowerCase()) &&
      !HOP_BY_HOP_HEADERS.has(name.toLowerCase()) &&
      value !== undefined
    ) {
      headers[name] = value;
    }
  }
  if (req.headers.host) {
    headers['x-forwarded-host'] = req.headers.host;
  }
  headers['x-forwarded-proto'] = req.headers.host?.includes('localhost') ? 'http' : 'https';
  return headers;
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let totalBytes = 0;
    req.on('data', (chunk) => {
      totalBytes += chunk.length;
      if (totalBytes > MAX_PROXY_BODY_BYTES) {
        reject(Object.assign(new Error('Request body too large'), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(chunks.length ? Buffer.concat(chunks) : undefined));
    req.on('error', reject);
  });
}

function copyResponseHeaders(upstream, res) {
  upstream.headers.forEach((value, name) => {
    if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase())) {
      res.setHeader(name, value);
    }
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function transientErrorCode(err) {
  // node-fetch / undici wraps the underlying syscall error in `cause`.
  const code = err?.code || err?.cause?.code;
  if (code && TRANSIENT_NETWORK_CODES.has(code)) return code;
  return null;
}

const SLOW_ENDPOINTS = ['/social/generate-image-actual', '/social/generate-pack'];
const DEFAULT_UPSTREAM_TIMEOUT_MS = 60_000;
const SLOW_UPSTREAM_TIMEOUT_MS = 200_000;

function upstreamTimeoutMs(path) {
  const apiPath = path.replace(/^\/api(?=\/|$)/, '') || '/';
  if (SLOW_ENDPOINTS.some((ep) => apiPath.startsWith(ep))) return SLOW_UPSTREAM_TIMEOUT_MS;
  return DEFAULT_UPSTREAM_TIMEOUT_MS;
}

export default async function handler(req, res) {
  let targetUrl;
  try {
    targetUrl = buildTargetUrl(req);
  } catch (err) {
    res.status(err.statusCode || 400).json({ detail: err.message || 'Invalid API request' });
    return;
  }
  const hasBody = !['GET', 'HEAD'].includes(req.method);
  let body;
  try {
    body = hasBody ? await readRequestBody(req) : undefined;
  } catch (err) {
    res.status(err.statusCode || 400).json({ detail: err.message || 'Invalid request body' });
    return;
  }
  const headers = copyRequestHeaders(req);
  const timeoutMs = upstreamTimeoutMs(req.url);

  let lastError;
  for (let attempt = 1; attempt <= MAX_PROXY_ATTEMPTS; attempt += 1) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const upstream = await fetch(targetUrl, {
        method: req.method,
        headers,
        body,
        redirect: 'manual',
        signal: controller.signal,
      });
      clearTimeout(timer);

      copyResponseHeaders(upstream, res);
      res.status(upstream.status);

      if (req.method === 'HEAD' || upstream.status === 204 || upstream.status === 304) {
        res.end();
        return;
      }

      const responseBody = Buffer.from(await upstream.arrayBuffer());
      res.send(responseBody);
      return;
    } catch (err) {
      lastError = err;
      const code = transientErrorCode(err);
      if (!code || attempt === MAX_PROXY_ATTEMPTS) break;
      // API container is probably still booting — wait briefly and retry.
      console.warn(
        `[api proxy] ${code} talking to ${API_URL} (attempt ${attempt}/${MAX_PROXY_ATTEMPTS}), retrying in ${PROXY_RETRY_DELAY_MS}ms`,
      );
      await sleep(PROXY_RETRY_DELAY_MS);
    }
  }

  const code = transientErrorCode(lastError);
  console.error(
    `[api proxy] giving up on ${req.method} ${targetUrl.href}: ${lastError?.message || lastError}`,
  );
  const detail = code
    ? `API backend at ${API_URL} is not reachable yet (${code}). It may still be starting — retry in a moment. ` +
      `If this persists, check the API container logs and confirm the web container's API_URL points at it.`
    : `API backend is unreachable at ${API_URL}. Check the web container API_URL setting and ensure the API container is running.`;

  res.status(502).json({ detail });
}
