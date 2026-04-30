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

export default async function handler(req, res) {
  const targetUrl = buildTargetUrl(req);
  const hasBody = !['GET', 'HEAD'].includes(req.method);

  try {
    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers: copyRequestHeaders(req),
      body: hasBody ? await readRequestBody(req) : undefined,
      redirect: 'manual',
    });

    copyResponseHeaders(upstream, res);
    res.status(upstream.status);

    if (req.method === 'HEAD' || upstream.status === 204 || upstream.status === 304) {
      res.end();
      return;
    }

    const body = Buffer.from(await upstream.arrayBuffer());
    res.send(body);
  } catch {
    res.status(502).json({
      detail: `API backend is unreachable at ${API_URL}. Check the web container API_URL setting and ensure the API container is running.`,
    });
  }
}
