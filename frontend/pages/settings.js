import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

// ── AI provider config ────────────────────────────────────────────────────────

const AI_PROVIDERS = [
  {
    value: 'openrouter',
    label: 'OpenRouter',
    description: 'Access 200+ models (GPT-4o, Claude, Mistral, Llama…) via a single API key.',
    keyLabel: 'OpenRouter API Key',
    keyPlaceholder: 'sk-or-v1-…',
    keyHelp: 'Get your key at openrouter.ai/keys',
    defaultBase: 'https://openrouter.ai/api/v1',
    baseLabel: 'Base URL',
    basePlaceholder: 'https://openrouter.ai/api/v1',
    baseHelp: 'Usually the default. Only change if using a proxy.',
    models: [
      { value: 'openai/gpt-4o',             label: 'GPT-4o (OpenAI)' },
      { value: 'openai/gpt-4o-mini',         label: 'GPT-4o Mini (fast, cheap)' },
      { value: 'anthropic/claude-3.5-sonnet',label: 'Claude 3.5 Sonnet (Anthropic)' },
      { value: 'anthropic/claude-3-haiku',   label: 'Claude 3 Haiku (fast)' },
      { value: 'mistralai/mistral-large',    label: 'Mistral Large' },
      { value: 'meta-llama/llama-3.1-70b-instruct', label: 'Llama 3.1 70B (Meta)' },
      { value: 'google/gemini-flash-1.5',    label: 'Gemini Flash 1.5 (Google)' },
    ],
  },
  {
    value: 'openai',
    label: 'OpenAI',
    description: 'Direct OpenAI API. Uses GPT-4o or GPT-4o Mini.',
    keyLabel: 'OpenAI API Key',
    keyPlaceholder: 'sk-…',
    keyHelp: 'Get your key at platform.openai.com/api-keys',
    defaultBase: 'https://api.openai.com/v1',
    baseLabel: 'Base URL (optional override)',
    basePlaceholder: 'https://api.openai.com/v1',
    baseHelp: 'Leave blank to use the default.',
    models: [
      { value: 'gpt-4o',         label: 'GPT-4o' },
      { value: 'gpt-4o-mini',    label: 'GPT-4o Mini (fast, cheap)' },
      { value: 'gpt-4-turbo',    label: 'GPT-4 Turbo' },
    ],
  },
  {
    value: 'ollama',
    label: 'Ollama (local)',
    description: 'Fully self-hosted. Runs models locally on your Unraid server.',
    keyLabel: 'API Key (leave blank for local)',
    keyPlaceholder: '(usually not required)',
    keyHelp: 'Ollama does not require an API key by default.',
    defaultBase: 'http://ollama.local:11434',
    baseLabel: 'Ollama Base URL',
    basePlaceholder: 'http://192.168.1.x:11434',
    baseHelp: 'The URL of your Ollama instance on the local network.',
    models: [
      { value: 'llama3.2',       label: 'Llama 3.2 (3B, fast)' },
      { value: 'llama3.1',       label: 'Llama 3.1 (8B)' },
      { value: 'llama3.1:70b',   label: 'Llama 3.1 70B (slow, high quality)' },
      { value: 'mistral',        label: 'Mistral 7B' },
      { value: 'gemma2',         label: 'Gemma 2 (Google)' },
      { value: 'qwen2.5:14b',    label: 'Qwen 2.5 14B' },
    ],
  },
];

// ── Integration config ────────────────────────────────────────────────────────

const INTEGRATION_FIELDS = {
  google_calendar: {
    label: 'Google',
    icon: '📅',
    logoDomain: 'google.com',
    description: 'Connect once for Calendar and Business Profile.',
    authType: 'oauth',
    connectLabel: 'Connect with Google',
    connectStyle: 'bg-blue-600 hover:bg-blue-700 border-blue-600',
    group: 'google',
    fields: [
      { key: 'client_id',     label: 'Client ID',     placeholder: 'From Google Cloud Console → OAuth 2.0 Client IDs', help: 'console.cloud.google.com → APIs & Services → Credentials → OAuth 2.0 Client IDs' },
      { key: 'client_secret', label: 'Client Secret', placeholder: 'Client Secret from Google Cloud Console', type: 'password', help: 'Same credential as the Client ID above' },
      { key: 'calendar_id',   label: 'Calendar ID (optional)', placeholder: 'primary or your@gmail.com', help: 'Leave blank to use your primary calendar. Found in Google Calendar settings → Integrate calendar.' },
    ],
  },
  google_business: {
    label: 'Google Business Profile',
    icon: '🗺️',
    logoDomain: 'business.google.com',
    description: 'Uses the shared Google OAuth connection above.',
    authType: 'shared_oauth',
    sharedProvider: 'google_calendar',
    sharedLabel: 'Google',
    group: 'google',
    fields: [],
  },
  meta: {
    label: 'Meta (Facebook & Instagram)',
    icon: '📘',
    logoDomain: 'facebook.com',
    description: 'Connect your Facebook Page and Instagram Business account for publishing.',
    authType: 'oauth',
    connectLabel: 'Connect with Meta',
    connectStyle: 'bg-[#1877F2] hover:bg-[#166FE5] border-[#1877F2]',
    fields: [
      { key: 'client_id',     label: 'App ID',     placeholder: 'Meta App ID from developers.facebook.com', help: 'developers.facebook.com → Your App → Settings → Basic → App ID' },
      { key: 'client_secret', label: 'App Secret', placeholder: 'App Secret from developers.facebook.com', type: 'password', help: 'developers.facebook.com → Your App → Settings → Basic → App Secret' },
    ],
  },
  jobber: {
    label: 'Jobber',
    icon: '🔧',
    logoDomain: 'jobber.com',
    description: 'Show upcoming jobs and job status on the dashboard.',
    authType: 'oauth',
    connectLabel: 'Connect with Jobber',
    connectStyle: 'bg-orange-500 hover:bg-orange-600 border-orange-500',
    fields: [
      { key: 'client_id',     label: 'Client ID',     placeholder: 'Client ID from Jobber Developer Center', help: 'developer.getjobber.com → Your App → Client ID' },
      { key: 'client_secret', label: 'Client Secret', placeholder: 'Client Secret from Jobber Developer Center', type: 'password', help: 'developer.getjobber.com → Your App → Client Secret' },
    ],
  },
  immich: {
    label: 'Immich',
    icon: '🖼️',
    logoDomain: 'immich.app',
    description: 'Connect source albums and recent photo context.',
    authType: 'api_key',
    fields: [
      { key: 'base_url', label: 'Immich Base URL', placeholder: 'http://192.168.1.x:2283', help: 'Your Immich server URL on the local network' },
      { key: 'api_key',  label: 'Immich API Key',  placeholder: 'API key from Immich settings', type: 'password', help: 'Immich → Account → API Keys → New API Key' },
    ],
  },
  'immich-gpt': {
    label: 'Immich-GPT',
    icon: '🤖',
    description: 'Classify photos between personal, business, and social candidates.',
    authType: 'api_key',
    fields: [
      { key: 'base_url', label: 'Immich-GPT Base URL', placeholder: 'http://192.168.1.x:3000', help: 'Your Immich-GPT service URL on the local network' },
      { key: 'api_key',  label: 'Immich-GPT API Key',  placeholder: 'Service API key or token', type: 'password', help: 'Used by processing summaries and image classification flows' },
    ],
  },
  'paperless-gpt': {
    label: 'Paperless-GPT',
    icon: '🤖',
    description: 'Read AI-processed documents through the BricoproHQ API endpoint.',
    authType: 'api_key',
    fields: [
      { key: 'base_url', label: 'Paperless-GPT URL', placeholder: 'http://paperless-gpt:8080', help: 'Enter the Paperless-GPT service root only, not /api/bricoprohq/v1. The test runs from the Bricopro HQ backend, so Docker installs may need a service hostname instead of a LAN or host-local address.' },
      { key: 'api_key',  label: 'API Key',  placeholder: 'pgpt_bhq_...', type: 'password', help: 'API key generated in Paperless-GPT for BricoproHQ.' },
    ],
  },
  paperless: {
    label: 'Paperless-ngx',
    icon: '📄',
    logoDomain: 'docs.paperless-ngx.com',
    description: 'Show recent documents and pending review queue.',
    authType: 'api_key',
    fields: [
      { key: 'base_url', label: 'Paperless Base URL', placeholder: 'http://192.168.1.x:8000', help: 'Your Paperless-ngx server URL' },
      { key: 'api_key',  label: 'Auth Token',          placeholder: 'Token from Paperless admin', type: 'password', help: 'Paperless → Admin → Auth Token' },
    ],
  },
};

const INTEGRATION_ORDER = [
  'google_calendar', 'google_business', 'meta', 'jobber',
  'immich', 'immich-gpt', 'paperless-gpt', 'paperless',
];

const SETTINGS_TABS = [
  { key: 'general', label: 'General' },
  { key: 'ai', label: 'AI Provider' },
  { key: 'integrations', label: 'Integrations' },
  { key: 'social', label: 'Social Studio' },
];

// ── Social Studio settings defaults ───────────────────────────────────────────

const SS_DEFAULTS = {
  default_album_id: '',
  image_model: 'openai/gpt-4o-mini',
  image_generation_model: '',
  copy_model: 'openai/gpt-4o-mini',
  default_language: 'fr',
  default_platforms: 'facebook,instagram,gbp',
  default_tone: 'local',
  default_city: 'Montréal',
  default_cta: 'request_quote',
  brand_voice: 'Friendly, local, practical, trustworthy Bricopro expert.',
  image_picker_prompt: 'Pick clear project photos to provide context for AI copy and to use in the post.',
  copy_prompt: 'Write practical, local, trustworthy Bricopro social posts based only on the provided job details and selected images.',
  facebook_prompt: 'Facebook: conversational, helpful, local, and clear about the service.',
  instagram_prompt: 'Instagram: concise caption, strong opening line, tasteful emojis, and relevant hashtags.',
  gbp_prompt: 'Google Business Profile: professional, service-focused, local, and direct.',
  before_after_prompt: 'If the user marks photos as before/after candidates, propose or generate a clean side-by-side montage without inventing results.',
  safety_prompt: 'Never invent reviews, client names, addresses, prices, certifications, or regulated trade work.',
  facebook_account: '',
  instagram_account: '',
  google_business_account: '',
  meta_account_id: '',
  google_ads_account_id: '',
  meta_ads_account: '',
  google_ads_account: '',
  before_after_enabled: 'true',
};

async function parseApiResponse(response, fallbackMessage) {
  const text = await response.text();
  if (!text) return {};
  try {
    const data = JSON.parse(text);
    return sanitizeApiPayload(data, fallbackMessage);
  } catch (err) {
    const detail = summarizeTextResponse(text, response.headers.get('content-type'), fallbackMessage);
    return { detail, message: detail };
  }
}

function sanitizeApiPayload(data, fallbackMessage = 'Request failed') {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return data;
  return {
    ...data,
    detail: typeof data.detail === 'string'
      ? summarizeTextResponse(data.detail, '', fallbackMessage)
      : data.detail,
    message: typeof data.message === 'string'
      ? summarizeTextResponse(data.message, '', fallbackMessage)
      : data.message,
  };
}

function formatErrorMessage(err, fallbackMessage = 'Request failed') {
  const message = err?.message || String(err || '');
  const sanitized = summarizeTextResponse(message.replace(/^Error:\s*/, ''), '', fallbackMessage);
  return err?.message ? `Error: ${sanitized}` : sanitized;
}

function errorMessage(data, fallbackMessage = 'Request failed') {
  if (data?.detail && typeof data.detail === 'object') {
    return data.detail.message || data.detail.hint || data.message || fallbackMessage;
  }
  return data?.detail || data?.message || fallbackMessage;
}

function errorDiagnostics(data) {
  const detail = data?.detail;
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return [];
  return [
    detail.type ? `Type: ${detail.type}` : '',
    detail.upstream_status ? `Upstream status: ${detail.upstream_status}` : '',
    detail.target_url ? `Target: ${detail.target_url}` : '',
    detail.configured_base_url ? `Configured base URL: ${detail.configured_base_url}` : '',
    detail.hint ? `Hint: ${detail.hint}` : '',
    detail.response_summary ? `Response: ${detail.response_summary}` : '',
  ].filter(Boolean);
}

function summarizeTextResponse(text, contentType = '', fallbackMessage = 'Request failed') {
  const raw = (text || '').trim();
  if (!raw) return fallbackMessage;
  if (isHtmlResponse(raw, contentType)) {
    const title = raw.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1];
    const summary = stripHtml(title || raw);
    return summary
      ? `Server returned HTML instead of JSON: ${summary}`
      : 'Server returned HTML instead of JSON. Check the configured URL and reverse proxy.';
  }
  return raw;
}

function isHtmlResponse(text, contentType = '') {
  const lowerType = (contentType || '').toLowerCase();
  const lowerText = text.trim().toLowerCase();
  return (
    lowerType.includes('html') ||
    /^<(?:!doctype html|html|head|body|title)\b/.test(lowerText) ||
    /<(?:!doctype html|html|head|body|title)\b/.test(lowerText.slice(0, 500))
  );
}

function stripHtml(text) {
  return (text || '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 300);
}

// ── Components ────────────────────────────────────────────────────────────────

function IntegrationIcon({ meta }) {
  if (meta.logoDomain) {
    return (
      <span className="w-8 h-8 rounded-xl bg-white border border-gray-100 flex items-center justify-center overflow-hidden">
        <img
          src={`https://www.google.com/s2/favicons?domain=${meta.logoDomain}&sz=64`}
          alt=""
          className="w-5 h-5 object-contain"
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      </span>
    );
  }
  return <span className="text-lg">{meta.icon}</span>;
}

function AiProviderSection({ settings, onSave, onTest }) {
  const currentProvider = settings.ai_provider || 'openrouter';
  const [provider, setProvider] = useState(currentProvider);
  const [apiKey, setApiKey] = useState(settings.ai_api_key || '');
  const [baseUrl, setBaseUrl] = useState(settings.ai_base_url || '');
  const [model, setModel] = useState(settings.ai_model || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const handleProviderChange = (val) => {
    setProvider(val);
    const meta = AI_PROVIDERS.find((p) => p.value === val);
    if (meta) setBaseUrl(meta.defaultBase);
    setModel('');
    setTestResult(null);
  };

  const meta = AI_PROVIDERS.find((p) => p.value === provider) || AI_PROVIDERS[0];

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave({ ai_provider: provider, ai_api_key: apiKey, ai_base_url: baseUrl, ai_model: model });
    setSaved(true);
    setSaving(false);
    setTimeout(() => setSaved(false), 2500);
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await onSave({ ai_provider: provider, ai_api_key: apiKey, ai_base_url: baseUrl, ai_model: model });
      const r = await onTest();
      setTestResult(r);
    } catch (err) {
      setTestResult({ ok: false, message: formatErrorMessage(err, 'Test failed') });
    }
    setTesting(false);
  };

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-semibold text-gray-800">AI Provider</h3>
          <p className="text-sm text-gray-500 mt-0.5">Used for social content generation in the AI Social Studio.</p>
        </div>
        {settings.ai_provider && (
          <span className="badge bg-green-100 text-green-700">{settings.ai_provider} configured</span>
        )}
      </div>

      <form onSubmit={save} className="space-y-5">
        <div>
          <label className="label">Provider</label>
          <div className="flex gap-1 p-1 bg-brand-700 rounded-lg w-fit">
            {AI_PROVIDERS.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => handleProviderChange(p.value)}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  provider === p.value
                    ? 'bg-white text-brand-600 shadow-sm font-semibold'
                    : 'text-brand-300 hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-2">{meta.description}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">{meta.keyLabel}</label>
            <input
              className="input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={meta.keyPlaceholder}
              autoComplete="off"
            />
            <p className="text-xs text-gray-400 mt-1">{meta.keyHelp}</p>
          </div>
          <div>
            <label className="label">Model</label>
            <select className="select" value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">Default ({meta.models[0]?.label})</option>
              {meta.models.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="col-span-full">
            <label className="label">{meta.baseLabel}</label>
            <input
              className="input"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={meta.basePlaceholder}
            />
            <p className="text-xs text-gray-400 mt-1">{meta.baseHelp}</p>
          </div>
        </div>

        {testResult && (
          <div className={`text-sm rounded-lg px-4 py-2.5 ${testResult.ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
            {testResult.ok ? '✓ ' : '✗ '}{testResult.message}
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <button type="submit" className="btn-primary text-sm" disabled={saving}>
            {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save AI Settings'}
          </button>
          <button type="button" className="btn-secondary text-sm" onClick={testConnection} disabled={testing || saving}>
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
        </div>
      </form>
    </div>
  );
}

function IntegrationSection({ providerKey, meta, integration, integrationsByProvider, onSave, onTest, onOAuthConnect, onDisconnect }) {
  const buildForm = (intg) => {
    const configFields = intg?.config_fields || {};
    const f = { base_url: intg?.base_url || '' };
    meta.fields.forEach(({ key }) => {
      if (key !== 'base_url') f[key] = configFields[key] || '';
    });
    return f;
  };

  const [form, setForm] = useState(() => buildForm(integration));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    setForm(buildForm(integration));
  }, [integration]); // eslint-disable-line

  const isOAuth = meta.authType === 'oauth';
  const isSharedOAuth = meta.authType === 'shared_oauth';
  const isApiKey = meta.authType === 'api_key';
  const sharedIntegration = isSharedOAuth ? integrationsByProvider?.[meta.sharedProvider] : null;
  const oauthConnected = isSharedOAuth ? sharedIntegration?.oauth_connected : integration?.oauth_connected;
  const oauthProviderKey = isSharedOAuth ? meta.sharedProvider : providerKey;
  const isConnected = integration?.status === 'ok' || (oauthConnected && integration?.status !== 'error');
  const statusLabel = isConnected ? 'Connected' : integration?.status === 'error' ? 'Error' : 'Not connected';
  const statusColor = isConnected
    ? 'bg-green-100 text-green-700'
    : integration?.status === 'error'
      ? 'bg-red-100 text-red-600'
      : 'bg-gray-100 text-gray-500';

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setTestResult(null);
    try {
      await onSave(providerKey, form);
      setSaved(true);
      setTestResult({ ok: true, message: 'Saved.' });
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setTestResult({ ok: false, message: formatErrorMessage(err, 'Save failed') });
    } finally {
      setSaving(false);
    }
  };

  const connect = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await onSave(providerKey, form);
      const result = await onTest(providerKey);
      setTestResult(result);
    } catch (err) {
      setTestResult({ ok: false, message: formatErrorMessage(err, 'Connection test failed') });
    } finally {
      setTesting(false);
    }
  };

  const oauthConnect = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await onSave(providerKey, form);
      const result = await onOAuthConnect(oauthProviderKey);
      if (!result.ok) {
        setTestResult(result);
      }
    } catch (err) {
      setTestResult({ ok: false, message: formatErrorMessage(err, 'OAuth connection failed') });
    } finally {
      setTesting(false);
    }
  };

  const disconnect = async () => {
    setDisconnecting(true);
    if (isApiKey) {
      await onDisconnect(providerKey, true);
    } else {
      await onDisconnect(providerKey, false);
    }
    setTestResult(null);
    setDisconnecting(false);
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IntegrationIcon meta={meta} />
          <div>
            <h3 className="font-semibold text-gray-800">{meta.label}</h3>
            <p className="text-xs text-gray-400">{meta.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`badge ${statusColor}`}>
            {statusLabel}
            {integration?.last_sync_at ? ` · ${new Date(integration.last_sync_at).toLocaleDateString()}` : ''}
          </span>
        </div>
      </div>

      <form onSubmit={save} className="space-y-3">
        {isSharedOAuth && (
          <div className="rounded-lg bg-blue-50 text-blue-700 px-4 py-3 text-sm">
            Uses the shared {meta.sharedLabel || 'OAuth'} connection. Connect or disconnect Google once to enable both
            Calendar and Business Profile.
          </div>
        )}

        {meta.fields.map(({ key, label, placeholder, type, help }) => (
          <div key={key}>
            <label className="label">{label}</label>
            <input
              className="input"
              value={form[key] || ''}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              placeholder={placeholder}
              type={type || 'text'}
              autoComplete="off"
            />
            {help && <p className="text-xs text-gray-400 mt-1">{help}</p>}
          </div>
        ))}

        {testResult && (
          <div className={`text-sm rounded-lg px-4 py-2.5 ${testResult.ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
            <div>{testResult.message}</div>
            {Array.isArray(testResult.diagnostics) && testResult.diagnostics.length > 0 && (
              <ul className="mt-2 list-disc pl-5 space-y-1 text-xs opacity-90">
                {testResult.diagnostics.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          {!isSharedOAuth && (
            <button type="submit" className="btn-primary text-sm" disabled={saving}>
              {saving ? 'Saving...' : saved ? 'Saved' : 'Save'}
            </button>
          )}

          {isOAuth || isSharedOAuth ? (
            oauthConnected ? (
              <>
                <button
                  type="button"
                  className="btn-secondary text-sm"
                  onClick={connect}
                  disabled={testing || saving}
                >
                  {testing ? 'Testing…' : 'Test Connection'}
                </button>
                <button
                  type="button"
                  className="btn-secondary text-sm text-red-600 border-red-200 hover:bg-red-50"
                  onClick={disconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? 'Disconnecting…' : 'Disconnect'}
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={oauthConnect}
                className={`btn-primary text-sm ${meta.connectStyle || 'bg-brand-600 hover:bg-brand-700'}`}
                disabled={testing || saving}
              >
                {testing ? 'Connecting…' : (meta.connectLabel || `Connect with ${meta.sharedLabel || meta.label}`)}
              </button>
            )
          ) : (
            <>
              <button
                type="button"
                className="btn-secondary text-sm"
                onClick={connect}
                disabled={testing || saving}
              >
                {testing ? 'Testing…' : isConnected ? 'Test Connection' : 'Connect'}
              </button>
              {isConnected && (
                <button
                  type="button"
                  className="btn-secondary text-sm text-red-600 border-red-200 hover:bg-red-50"
                  onClick={disconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? 'Disconnecting…' : 'Disconnect'}
                </button>
              )}
            </>
          )}
        </div>
      </form>
    </div>
  );
}

function GoogleIntegrationGroup({ integrationsByProvider, onSave, onTest, onOAuthConnect, onDisconnect }) {
  const calMeta = INTEGRATION_FIELDS.google_calendar;
  const gbpMeta = INTEGRATION_FIELDS.google_business;
  const calIntegration = integrationsByProvider.google_calendar || null;
  const gbpIntegration = integrationsByProvider.google_business || null;
  const oauthConnected = calIntegration?.oauth_connected;
  const isConnected = calIntegration?.status === 'ok' || (oauthConnected && calIntegration?.status !== 'error');

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IntegrationIcon meta={calMeta} />
          <div>
            <h3 className="font-semibold text-gray-800">Google Services</h3>
            <p className="text-xs text-gray-400">Single OAuth connection for Calendar and Business Profile.</p>
          </div>
        </div>
        <span className={`badge ${isConnected ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
          {isConnected ? 'Connected' : 'Not connected'}
          {calIntegration?.last_sync_at ? ` · ${new Date(calIntegration.last_sync_at).toLocaleDateString()}` : ''}
        </span>
      </div>

      {oauthConnected && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          <div className="rounded-lg border border-gray-100 p-3 flex items-center gap-2">
            <span className="text-lg">📅</span>
            <div>
              <p className="text-sm font-medium text-gray-800">Calendar</p>
              <p className="text-xs text-gray-400">{calIntegration?.status === 'ok' ? 'Active' : 'Connected'}</p>
            </div>
          </div>
          <div className="rounded-lg border border-gray-100 p-3 flex items-center gap-2">
            <span className="text-lg">🗺️</span>
            <div>
              <p className="text-sm font-medium text-gray-800">Business Profile</p>
              <p className="text-xs text-gray-400">{gbpIntegration?.status === 'ok' ? 'Active' : 'Connected'}</p>
            </div>
          </div>
        </div>
      )}

      <IntegrationSection
        providerKey="google_calendar"
        meta={{ ...calMeta, label: 'Google OAuth' }}
        integration={calIntegration}
        integrationsByProvider={integrationsByProvider}
        onSave={onSave}
        onTest={onTest}
        onOAuthConnect={onOAuthConnect}
        onDisconnect={onDisconnect}
      />
    </div>
  );
}

function SocialStudioSettingsInline({ apiFetch }) {
  const [form, setForm] = useState(SS_DEFAULTS);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const r = await apiFetch('/social/settings');
    if (r.ok) setForm({ ...SS_DEFAULTS, ...(await r.json()) });
  }, [apiFetch]);

  useEffect(() => { load(); }, []); // eslint-disable-line

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    await apiFetch('/social/settings', {
      method: 'PUT',
      body: JSON.stringify(form),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <form onSubmit={save} className="space-y-6">
      <section className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Immich source</h3>
        <div>
          <label className="label">Default Immich album ID</label>
          <input
            className="input"
            value={form.default_album_id}
            onChange={(e) => setForm({ ...form, default_album_id: e.target.value })}
            placeholder="Album UUID or friendly source name"
          />
          <p className="text-xs text-gray-400 mt-1">Used as the starting album for image candidate analysis.</p>
        </div>
      </section>

      <section className="card">
        <h3 className="font-semibold text-gray-800 mb-4">AI models</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Image analysis model</label>
            <input className="input" value={form.image_model} onChange={(e) => setForm({ ...form, image_model: e.target.value })} />
          </div>
          <div>
            <label className="label">Copywriting model</label>
            <input className="input" value={form.copy_model} onChange={(e) => setForm({ ...form, copy_model: e.target.value })} />
          </div>
          <div>
            <label className="label">Image generation model</label>
            <input className="input" value={form.image_generation_model} onChange={(e) => setForm({ ...form, image_generation_model: e.target.value })} placeholder="Optional image model" />
          </div>
          <div>
            <label className="label">Default language</label>
            <select className="select" value={form.default_language} onChange={(e) => setForm({ ...form, default_language: e.target.value })}>
              <option value="fr">Français</option>
              <option value="en">English</option>
              <option value="bilingual">Bilingual</option>
            </select>
          </div>
          <div>
            <label className="label">Default platforms</label>
            <input className="input" value={form.default_platforms} onChange={(e) => setForm({ ...form, default_platforms: e.target.value })} />
          </div>
          <div>
            <label className="label">Default tone</label>
            <input className="input" value={form.default_tone} onChange={(e) => setForm({ ...form, default_tone: e.target.value })} placeholder="local, friendly, professional..." />
          </div>
          <div>
            <label className="label">Default city / neighbourhood</label>
            <input className="input" value={form.default_city} onChange={(e) => setForm({ ...form, default_city: e.target.value })} />
          </div>
          <div>
            <label className="label">Default CTA</label>
            <input className="input" value={form.default_cta} onChange={(e) => setForm({ ...form, default_cta: e.target.value })} />
          </div>
        </div>
      </section>

      <section className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Brand and publishing defaults</h3>
        <div className="space-y-4">
          <div>
            <label className="label">Brand voice</label>
            <textarea className="input h-24 resize-y" value={form.brand_voice} onChange={(e) => setForm({ ...form, brand_voice: e.target.value })} />
          </div>
          <div>
            <label className="label">Before / after generation</label>
            <select className="select" value={form.before_after_enabled} onChange={(e) => setForm({ ...form, before_after_enabled: e.target.value })}>
              <option value="true">Enabled when image pairs are available</option>
              <option value="false">Disabled</option>
            </select>
          </div>
        </div>
      </section>

      <section className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Workflow prompts</h3>
        <div className="space-y-4">
          <div>
            <label className="label">Image picker prompt</label>
            <textarea className="input h-20 resize-y" value={form.image_picker_prompt} onChange={(e) => setForm({ ...form, image_picker_prompt: e.target.value })} />
            <p className="text-xs text-gray-400 mt-1">Guidance shown in the image picker. The user selects images manually to provide context for AI copy and to include in posts.</p>
          </div>
          <div>
            <label className="label">Base copy prompt</label>
            <textarea className="input h-24 resize-y" value={form.copy_prompt} onChange={(e) => setForm({ ...form, copy_prompt: e.target.value })} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="label">Facebook prompt</label>
              <textarea className="input h-28 resize-y" value={form.facebook_prompt} onChange={(e) => setForm({ ...form, facebook_prompt: e.target.value })} />
            </div>
            <div>
              <label className="label">Instagram prompt</label>
              <textarea className="input h-28 resize-y" value={form.instagram_prompt} onChange={(e) => setForm({ ...form, instagram_prompt: e.target.value })} />
            </div>
            <div>
              <label className="label">GBP prompt</label>
              <textarea className="input h-28 resize-y" value={form.gbp_prompt} onChange={(e) => setForm({ ...form, gbp_prompt: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="label">Before / after prompt</label>
            <textarea className="input h-20 resize-y" value={form.before_after_prompt} onChange={(e) => setForm({ ...form, before_after_prompt: e.target.value })} />
          </div>
          <div>
            <label className="label">Safety / compliance prompt</label>
            <textarea className="input h-20 resize-y" value={form.safety_prompt} onChange={(e) => setForm({ ...form, safety_prompt: e.target.value })} />
          </div>
        </div>
      </section>

      <section className="card">
        <h3 className="font-semibold text-gray-800 mb-3">Social account connections</h3>
        <div className="flex items-start gap-3 p-3 bg-blue-50 border border-blue-100 rounded-lg mb-4">
          <span className="text-blue-500 mt-0.5">ℹ</span>
          <p className="text-sm text-blue-700">
            Facebook, Instagram, and Google Business Profile connections are managed via OAuth in the Integrations tab.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Default Facebook Page name / ID <span className="text-gray-400 font-normal">(optional override)</span></label>
            <input className="input" value={form.facebook_account} onChange={(e) => setForm({ ...form, facebook_account: e.target.value })} placeholder="Leave blank to use first connected page" />
          </div>
          <div>
            <label className="label">Default Instagram handle <span className="text-gray-400 font-normal">(optional override)</span></label>
            <input className="input" value={form.instagram_account} onChange={(e) => setForm({ ...form, instagram_account: e.target.value })} placeholder="@bricopro" />
          </div>
          <div>
            <label className="label">Meta Ads account ID</label>
            <input className="input" value={form.meta_ads_account || form.meta_account_id} onChange={(e) => setForm({ ...form, meta_ads_account: e.target.value, meta_account_id: e.target.value })} placeholder="act_XXXXXXXXXX" />
          </div>
          <div>
            <label className="label">Google Ads customer ID</label>
            <input className="input" value={form.google_ads_account || form.google_ads_account_id} onChange={(e) => setForm({ ...form, google_ads_account: e.target.value, google_ads_account_id: e.target.value })} placeholder="XXX-XXX-XXXX" />
          </div>
        </div>
      </section>

      <div className="flex gap-2">
        <button className="btn-primary" type="submit" disabled={saving}>
          {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save Social Studio Settings'}
        </button>
      </div>
    </form>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [integrations, setIntegrations] = useState([]);
  const [settings, setSettings] = useState({});
  const [oauthBanner, setOauthBanner] = useState(null);
  const [activeTab, setActiveTab] = useState('general');

  const testAiConnection = useCallback(async () => {
    const r = await apiFetch('/ai/test', { method: 'POST' });
    const data = await parseApiResponse(r, 'Test failed');
    if (r.ok) return { ok: true, message: data.message || 'Connection successful' };
    return { ok: false, message: data.detail || 'Test failed' };
  }, [apiFetch]);

  const loadIntegrations = useCallback(async () => {
    const r = await apiFetch('/integrations');
    if (r.ok) setIntegrations(await r.json());
  }, [apiFetch]);

  const loadSettings = useCallback(async () => {
    const r = await apiFetch('/settings');
    if (r.ok) {
      const all = await r.json();
      const map = {};
      all.forEach((s) => { map[s.key] = s.value; });
      setSettings(map);
    }
  }, [apiFetch]);

  useEffect(() => {
    if (!isLoggedIn) return;
    loadIntegrations();
    loadSettings();
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const tab = params.get('tab');
      if (tab && SETTINGS_TABS.some((t) => t.key === tab)) {
        setActiveTab(tab);
      }
      const connectedProvider = params.get('oauth_connected');
      const oauthError = params.get('oauth_error');
      const oauthProvider = params.get('oauth_provider');
      if (connectedProvider) {
        const label = INTEGRATION_FIELDS[connectedProvider]?.label || connectedProvider;
        setOauthBanner({ ok: true, message: `${label} connected successfully via OAuth!` });
        setActiveTab('integrations');
        window.history.replaceState({}, '', '/settings');
      } else if (oauthError) {
        const label = INTEGRATION_FIELDS[oauthProvider]?.label || oauthProvider || 'Integration';
        setOauthBanner({ ok: false, message: `${label} OAuth error: ${oauthError}` });
        setActiveTab('integrations');
        window.history.replaceState({}, '', '/settings');
      }
    }
  }, [isLoggedIn]); // eslint-disable-line

  const saveAiSettings = useCallback(async (vals) => {
    for (const [key, value] of Object.entries(vals)) {
      await apiFetch(`/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value: value || '' }) });
    }
    await loadSettings();
  }, [apiFetch, loadSettings]);

  const saveIntegration = useCallback(async (providerKey, form) => {
    const { base_url, ...rest } = form;
    const normalizedBaseUrl = providerKey === 'paperless-gpt'
      ? (base_url || '').trim().replace(/\/+$/, '')
      : (base_url || '');
    const r = await apiFetch(`/integrations/${providerKey}`, {
      method: 'PUT',
      body: JSON.stringify({ base_url: normalizedBaseUrl, config_json: JSON.stringify(rest) }),
    });
    const data = await parseApiResponse(r, 'Save failed');
    if (!r.ok) {
      throw new Error(errorMessage(data, 'Save failed'));
    }
    if (r.ok) {
      setIntegrations((prev) => prev.map((i) => (i.provider === providerKey ? data : i)));
    }
  }, [apiFetch]);

  const testIntegration = useCallback(async (providerKey) => {
    try {
      const r = await apiFetch(`/integrations/${providerKey}/test`, { method: 'POST' });
      const data = await parseApiResponse(r, 'Connection test failed');
      if (r.ok) {
        setIntegrations((prev) =>
          prev.map((i) => (i.provider === providerKey ? { ...i, status: 'ok' } : i))
        );
        return { ok: true, message: data.message || 'Connected.' };
      }
      setIntegrations((prev) =>
        prev.map((i) => (i.provider === providerKey ? { ...i, status: 'error' } : i))
      );
      return { ok: false, message: errorMessage(data, 'Check settings.'), diagnostics: errorDiagnostics(data) };
    } catch (err) {
      return { ok: false, message: formatErrorMessage(err, 'Connection test failed') };
    }
  }, [apiFetch]);

  const startOAuthConnect = useCallback(async (providerKey) => {
    try {
      const r = await apiFetch(`/integrations/${providerKey}/oauth/authorize?mode=json`);
      const data = await parseApiResponse(r, 'OAuth connection failed');
      if (!r.ok) {
        const message = data.detail === 'Missing bearer token'
          ? 'Sign in again.'
          : data.detail || 'Check settings.';
        return { ok: false, message };
      }
      if (!data.authorization_url) {
        return { ok: false, message: 'Check settings.' };
      }
      window.location.assign(data.authorization_url);
      return { ok: true, message: 'Redirecting...' };
    } catch (err) {
      return { ok: false, message: formatErrorMessage(err, 'OAuth connection failed') };
    }
  }, [apiFetch]);

  const disconnectIntegration = useCallback(async (providerKey, isApiKeyDisconnect = false) => {
    if (isApiKeyDisconnect) {
      await apiFetch(`/integrations/${providerKey}/disconnect`, { method: 'POST' });
    } else {
      await apiFetch(`/integrations/${providerKey}/oauth/disconnect`, { method: 'POST' });
    }
    await loadIntegrations();
  }, [apiFetch, loadIntegrations]);

  if (!isLoggedIn) return <LoginForm />;

  const intMap = {};
  integrations.forEach((i) => { intMap[i.provider] = i; });

  const nonGoogleIntegrations = INTEGRATION_ORDER.filter(
    (key) => !INTEGRATION_FIELDS[key]?.group
  );

  return (
    <div className="p-6 max-w-3xl">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Settings</h2>
      <p className="text-gray-500 text-sm mb-5">Configure app preferences, AI, integrations, and Social Studio.</p>

      <div className="flex flex-wrap gap-2 mb-6 border-b border-gray-200">
        {SETTINGS_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              activeTab === tab.key
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'general' && (
        <section className="card">
          <h3 className="font-semibold text-gray-800">General</h3>
          <p className="text-sm text-gray-500 mt-1">
            Core app settings live here. More general preferences will appear in this tab as they are added.
          </p>
        </section>
      )}

      {activeTab === 'ai' && (
        <section>
          <AiProviderSection settings={settings} onSave={saveAiSettings} onTest={testAiConnection} />
        </section>
      )}

      {activeTab === 'integrations' && oauthBanner && (
        <div className={`mb-6 rounded-lg px-4 py-3 flex items-center justify-between ${oauthBanner.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          <span className="text-sm">{oauthBanner.ok ? '✓ ' : '✗ '}{oauthBanner.message}</span>
          <button className="text-xs opacity-60 hover:opacity-100 ml-4" onClick={() => setOauthBanner(null)}>Dismiss</button>
        </div>
      )}

      {activeTab === 'integrations' && (
        <section>
          <h3 className="text-base font-semibold text-gray-800 mb-3">Integrations</h3>
          <p className="text-sm text-gray-500 mb-4">
            All credentials are stored in the database. The app reads them on each refresh — no restart needed.
          </p>
          <div className="grid grid-cols-1 gap-4">
            <GoogleIntegrationGroup
              integrationsByProvider={intMap}
              onSave={saveIntegration}
              onTest={testIntegration}
              onOAuthConnect={startOAuthConnect}
              onDisconnect={disconnectIntegration}
            />

            {nonGoogleIntegrations.map((key) => {
              const meta = INTEGRATION_FIELDS[key];
              if (!meta) return null;
              return (
                <IntegrationSection
                  key={key}
                  providerKey={key}
                  meta={meta}
                  integration={intMap[key] || null}
                  integrationsByProvider={intMap}
                  onSave={saveIntegration}
                  onTest={testIntegration}
                  onOAuthConnect={startOAuthConnect}
                  onDisconnect={disconnectIntegration}
                />
              );
            })}
          </div>
        </section>
      )}

      {activeTab === 'social' && (
        <section>
          <h3 className="text-base font-semibold text-gray-800 mb-3">Social Studio Settings</h3>
          <p className="text-sm text-gray-500 mb-4">
            Configure Immich albums, model choices, account defaults, and workflow prompts.
          </p>
          <SocialStudioSettingsInline apiFetch={apiFetch} />
        </section>
      )}
    </div>
  );
}
