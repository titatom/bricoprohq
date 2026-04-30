import Link from 'next/link';
import { useEffect, useState, useCallback } from 'react';
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
    label: 'Google Calendar',
    icon: '📅',
    description: 'Show upcoming events on the dashboard.',
    authType: 'api_key',
    fields: [
      { key: 'api_key',     label: 'Google API Key',     placeholder: 'AIza…', type: 'password', help: 'Enable Calendar API at console.cloud.google.com → API Keys' },
      { key: 'calendar_id', label: 'Calendar ID',        placeholder: 'your@gmail.com or id@group.calendar.google.com', help: 'Found in Google Calendar settings → Integrate calendar' },
    ],
  },
  jobber: {
    label: 'Jobber',
    icon: '🔧',
    description: 'Show upcoming jobs and job status on the dashboard.',
    authType: 'oauth',
    fields: [
      { key: 'client_id',     label: 'Client ID',     placeholder: 'Client ID from Jobber Developer Center', help: 'developer.getjobber.com → Your App → Client ID' },
      { key: 'client_secret', label: 'Client Secret', placeholder: 'Client Secret from Jobber Developer Center', type: 'password', help: 'developer.getjobber.com → Your App → Client Secret' },
    ],
  },
  immich: {
    label: 'Immich',
    icon: '🖼️',
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
  paperless: {
    label: 'Paperless-ngx',
    icon: '📄',
    description: 'Show recent documents and pending review queue.',
    authType: 'api_key',
    fields: [
      { key: 'base_url', label: 'Paperless Base URL', placeholder: 'http://192.168.1.x:8000', help: 'Your Paperless-ngx server URL' },
      { key: 'api_key',  label: 'Auth Token',          placeholder: 'Token from Paperless admin', type: 'password', help: 'Paperless → Admin → Auth Token' },
    ],
  },
};

// ── Components ────────────────────────────────────────────────────────────────

function AiProviderSection({ settings, onSave, onTest }) {
  const currentProvider = settings.ai_provider || 'openrouter';
  const providerMeta = AI_PROVIDERS.find((p) => p.value === currentProvider) || AI_PROVIDERS[0];

  const [provider, setProvider] = useState(currentProvider);
  const [apiKey, setApiKey] = useState(settings.ai_api_key || '');
  const [baseUrl, setBaseUrl] = useState(settings.ai_base_url || '');
  const [model, setModel] = useState(settings.ai_model || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // When provider changes, reset base URL to default and clear model
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
      setTestResult({ ok: false, message: String(err) });
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
        {/* Provider tabs */}
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
          {/* API Key */}
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

          {/* Model */}
          <div>
            <label className="label">Model</label>
            <select
              className="select"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">Default ({meta.models[0]?.label})</option>
              {meta.models.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">
              {provider === 'openrouter' ? 'Model is passed as the OpenAI model field.' : 'Select the model to use for generation.'}
            </p>
          </div>

          {/* Base URL */}
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

        {/* Test result */}
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

function IntegrationSection({ providerKey, meta, integration, onSave, onTest, onDisconnect }) {
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

  // Sync form when integration data loads/changes from parent
  useEffect(() => {
    setForm(buildForm(integration));
  }, [integration]); // eslint-disable-line

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setTestResult(null);
    await onSave(providerKey, form);
    setSaved(true);
    setSaving(false);
    setTimeout(() => setSaved(false), 2000);
  };

  const connect = async () => {
    setTesting(true);
    setTestResult(null);
    const result = await onTest(providerKey);
    setTestResult(result);
    setTesting(false);
  };

  const disconnect = async () => {
    setDisconnecting(true);
    await onDisconnect(providerKey);
    setTestResult(null);
    setDisconnecting(false);
  };

  const isOAuth = meta.authType === 'oauth';
  const oauthConnected = integration?.oauth_connected;

  const statusColor =
    integration?.status === 'ok'            ? 'bg-green-100 text-green-700' :
    integration?.status === 'not_connected'  ? 'bg-gray-100 text-gray-500'   :
    integration?.status === 'error'          ? 'bg-red-100 text-red-600'     :
    'bg-gray-100 text-gray-500';

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-lg">{meta.icon}</span>
          <div>
            <h3 className="font-semibold text-gray-800">{meta.label}</h3>
            <p className="text-xs text-gray-400">{meta.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isOAuth && oauthConnected && (
            <span className="badge bg-green-100 text-green-700">Connected via OAuth</span>
          )}
          <span className={`badge ${statusColor}`}>
            {integration?.status || 'unknown'}
            {integration?.last_sync_at ? ` · ${new Date(integration.last_sync_at).toLocaleDateString()}` : ''}
          </span>
        </div>
      </div>

      <form onSubmit={save} className="space-y-3">
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
            {testResult.ok ? '✓ ' : '✗ '}{testResult.message}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <button type="submit" className="btn-primary text-sm" disabled={saving}>
            {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save'}
          </button>

          {isOAuth ? (
            oauthConnected ? (
              <button
                type="button"
                className="btn-secondary text-sm text-red-600 border-red-200 hover:bg-red-50"
                onClick={disconnect}
                disabled={disconnecting}
              >
                {disconnecting ? 'Disconnecting…' : 'Disconnect'}
              </button>
            ) : (
              <a
                href="/api/integrations/jobber/oauth/authorize"
                className="btn-primary text-sm bg-orange-500 hover:bg-orange-600 border-orange-500"
              >
                Connect with Jobber
              </a>
            )
          ) : (
            <button
              type="button"
              className="btn-secondary text-sm"
              onClick={connect}
              disabled={testing || saving}
            >
              {testing ? 'Connecting…' : 'Test Connection'}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [integrations, setIntegrations] = useState([]);
  const [settings, setSettings] = useState({});
  const [oauthBanner, setOauthBanner] = useState(null);

  const testAiConnection = useCallback(async () => {
    const r = await apiFetch('/ai/test', { method: 'POST' });
    const data = await r.json();
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
    // Check for OAuth callback result in query params
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('jobber_connected')) {
        setOauthBanner({ ok: true, message: 'Jobber connected successfully via OAuth!' });
        window.history.replaceState({}, '', '/settings');
      } else if (params.get('jobber_error')) {
        setOauthBanner({ ok: false, message: `Jobber OAuth error: ${params.get('jobber_error')}` });
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
    const r = await apiFetch(`/integrations/${providerKey}`, {
      method: 'PUT',
      body: JSON.stringify({ base_url: base_url || '', config_json: JSON.stringify(rest) }),
    });
    if (r.ok) {
      const updated = await r.json();
      setIntegrations((prev) => prev.map((i) => (i.provider === providerKey ? updated : i)));
    }
  }, [apiFetch]);

  const testIntegration = useCallback(async (providerKey) => {
    try {
      const r = await apiFetch(`/integrations/${providerKey}/test`, { method: 'POST' });
      const data = await r.json();
      if (r.ok) {
        setIntegrations((prev) =>
          prev.map((i) => (i.provider === providerKey ? { ...i, status: 'ok' } : i))
        );
        return { ok: true, message: data.message || 'Connection successful' };
      }
      setIntegrations((prev) =>
        prev.map((i) => (i.provider === providerKey ? { ...i, status: 'error' } : i))
      );
      return { ok: false, message: data.detail || 'Connection test failed' };
    } catch (err) {
      return { ok: false, message: String(err) };
    }
  }, [apiFetch]);

  const disconnectIntegration = useCallback(async (providerKey) => {
    if (providerKey === 'jobber') {
      await apiFetch('/integrations/jobber/oauth/disconnect', { method: 'POST' });
      await loadIntegrations();
    }
  }, [apiFetch, loadIntegrations]);

  if (!isLoggedIn) return <LoginForm />;

  const intMap = {};
  integrations.forEach((i) => { intMap[i.provider] = i; });

  return (
    <div className="p-6 max-w-3xl">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Settings</h2>
      <p className="text-gray-500 text-sm mb-8">Configure the AI provider and integration credentials. All values are saved to the database and persist across restarts.</p>

      <div className="card mb-8 border-l-4 border-accent-500">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-800">Social Studio Settings</h3>
            <p className="text-sm text-gray-500 mt-1">
              Configure Immich albums, model choices, account defaults, and KPI preferences separately from core integrations.
            </p>
          </div>
          <Link href="/settings/social-studio" className="btn-primary text-sm whitespace-nowrap">
            Open Social Studio Settings
          </Link>
        </div>
      </div>

      {/* AI Provider */}
      <section className="mb-8">
        <AiProviderSection settings={settings} onSave={saveAiSettings} onTest={testAiConnection} />
      </section>

      {/* OAuth result banner */}
      {oauthBanner && (
        <div className={`mb-6 rounded-lg px-4 py-3 flex items-center justify-between ${oauthBanner.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          <span className="text-sm">{oauthBanner.ok ? '✓ ' : '✗ '}{oauthBanner.message}</span>
          <button className="text-xs opacity-60 hover:opacity-100 ml-4" onClick={() => setOauthBanner(null)}>Dismiss</button>
        </div>
      )}

      {/* Integrations */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 mb-3">Integrations</h3>
        <p className="text-sm text-gray-500 mb-4">
          All credentials are stored in the database. The app reads them on each refresh — no restart needed.
        </p>
        <div className="grid grid-cols-1 gap-4">
          {Object.entries(INTEGRATION_FIELDS).map(([key, meta]) => (
            <IntegrationSection
              key={key}
              providerKey={key}
              meta={meta}
              integration={intMap[key] || null}
              onSave={saveIntegration}
              onTest={testIntegration}
              onDisconnect={disconnectIntegration}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
