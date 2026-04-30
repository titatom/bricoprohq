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

function buildTargetUrl(req) {
  const apiPath = req.url.replace(/^\/api(?=\/|$)/, '') || '/';
  return new URL(apiPath, API_URL.endsWith('/') ? API_URL : `${API_URL}/`);
}

function copyRequestHeaders(req) {
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase()) && value !== undefined) {
      headers[name] = value;
    }
  }
  return headers;
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
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

export default async function handler(req, res) {
  const targetUrl = buildTargetUrl(req);
  const hasBody = !['GET', 'HEAD'].includes(req.method);
  // Read the body once up-front so we can safely retry the upstream fetch.
  const body = hasBody ? await readRequestBody(req) : undefined;
  const headers = copyRequestHeaders(req);

  let lastError;
  for (let attempt = 1; attempt <= MAX_PROXY_ATTEMPTS; attempt += 1) {
    try {
      const upstream = await fetch(targetUrl, {
        method: req.method,
        headers,
        body,
        redirect: 'manual',
      });

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
