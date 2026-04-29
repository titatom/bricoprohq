import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

const INTEGRATION_FIELDS = {
  google_calendar: [
    { key: 'base_url',         label: 'Calendar ID / API URL', placeholder: 'your-calendar@group.calendar.google.com' },
    { key: 'api_key',          label: 'API Key / Service Account JSON path', placeholder: '/run/secrets/google-sa.json' },
  ],
  jobber: [
    { key: 'base_url',         label: 'Jobber API Base URL', placeholder: 'https://api.getjobber.com/api/graphql' },
    { key: 'api_key',          label: 'Jobber API Key', placeholder: 'Bearer token' },
  ],
  immich: [
    { key: 'base_url',         label: 'Immich Base URL', placeholder: 'http://immich.local:2283' },
    { key: 'api_key',          label: 'Immich API Key', placeholder: 'api-key-from-immich' },
  ],
  paperless: [
    { key: 'base_url',         label: 'Paperless Base URL', placeholder: 'http://paperless.local:8000' },
    { key: 'api_key',          label: 'Paperless API Token', placeholder: 'token-from-paperless' },
  ],
};

const AI_PROVIDERS = ['openai', 'openrouter', 'ollama'];

function IntegrationSection({ provider, integration, onSave }) {
  const fields = INTEGRATION_FIELDS[provider] || [];
  const config = integration ? (() => { try { return JSON.parse(integration.config_json || '{}'); } catch { return {}; } })() : {};
  const [form, setForm] = useState({ base_url: integration?.base_url || '', ...config });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave(provider, form);
    setSaved(true);
    setSaving(false);
    setTimeout(() => setSaved(false), 2000);
  };

  const statusColor =
    integration?.status === 'ok' ? 'text-green-600' :
    integration?.status === 'not_connected' ? 'text-red-500' :
    'text-yellow-600';

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-800 capitalize">{provider.replace('_', ' ')}</h3>
        <span className={`text-xs font-medium ${statusColor}`}>
          {integration?.status || 'unknown'}
          {integration?.last_sync_at && ` · synced ${new Date(integration.last_sync_at).toLocaleString()}`}
        </span>
      </div>
      <form onSubmit={save} className="space-y-3">
        {fields.map(({ key, label, placeholder }) => (
          <div key={key}>
            <label className="label">{label}</label>
            <input
              className="input"
              value={form[key] || ''}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              placeholder={placeholder}
              type={key === 'api_key' ? 'password' : 'text'}
              autoComplete="off"
            />
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button type="submit" className="btn-primary text-sm" disabled={saving}>
            {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function SettingsPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [integrations, setIntegrations] = useState([]);
  const [settings, setSettings] = useState([]);
  const [aiProvider, setAiProvider] = useState('openai');
  const [aiKey, setAiKey] = useState('');
  const [aiBase, setAiBase] = useState('');
  const [savingAi, setSavingAi] = useState(false);
  const [savedAi, setSavedAi] = useState(false);

  const loadIntegrations = useCallback(async () => {
    const r = await apiFetch('/integrations');
    if (r.ok) setIntegrations(await r.json());
  }, [apiFetch]);

  const loadSettings = useCallback(async () => {
    const r = await apiFetch('/settings');
    if (r.ok) {
      const all = await r.json();
      setSettings(all);
      const prov = all.find((s) => s.key === 'ai_provider');
      const key  = all.find((s) => s.key === 'ai_api_key');
      const base = all.find((s) => s.key === 'ai_base_url');
      if (prov) setAiProvider(prov.value);
      if (key)  setAiKey(key.value);
      if (base) setAiBase(base.value);
    }
  }, [apiFetch]);

  useEffect(() => {
    if (!isLoggedIn) return;
    loadIntegrations();
    loadSettings();
  }, [isLoggedIn]); // eslint-disable-line

  const saveIntegration = async (provider, form) => {
    const { base_url, ...rest } = form;
    await apiFetch(`/integrations/${provider}`, {
      method: 'PUT',
      body: JSON.stringify({ base_url: base_url || '', config_json: JSON.stringify(rest) }),
    });
    await loadIntegrations();
  };

  const saveAiSettings = async (e) => {
    e.preventDefault();
    setSavingAi(true);
    await apiFetch('/settings/ai_provider', { method: 'PUT', body: JSON.stringify({ value: aiProvider }) });
    await apiFetch('/settings/ai_api_key',  { method: 'PUT', body: JSON.stringify({ value: aiKey }) });
    await apiFetch('/settings/ai_base_url', { method: 'PUT', body: JSON.stringify({ value: aiBase }) });
    setSavedAi(true);
    setSavingAi(false);
    setTimeout(() => setSavedAi(false), 2000);
  };

  if (!isLoggedIn) return <LoginForm />;

  const intMap = {};
  integrations.forEach((i) => { intMap[i.provider] = i; });

  return (
    <div className="p-6 max-w-3xl">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Settings</h2>
      <p className="text-gray-500 text-sm mb-8">Configure integrations, AI provider, and app settings.</p>

      {/* AI Provider */}
      <section className="mb-8">
        <h3 className="text-base font-semibold text-gray-800 mb-3">AI Provider</h3>
        <div className="card">
          <form onSubmit={saveAiSettings} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Provider</label>
              <select className="select" value={aiProvider} onChange={(e) => setAiProvider(e.target.value)}>
                {AI_PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="label">API Key</label>
              <input
                className="input"
                type="password"
                value={aiKey}
                onChange={(e) => setAiKey(e.target.value)}
                placeholder="sk-…"
                autoComplete="off"
              />
            </div>
            {(aiProvider === 'openrouter' || aiProvider === 'ollama') && (
              <div className="col-span-full">
                <label className="label">Base URL</label>
                <input
                  className="input"
                  value={aiBase}
                  onChange={(e) => setAiBase(e.target.value)}
                  placeholder={aiProvider === 'ollama' ? 'http://ollama.local:11434' : 'https://openrouter.ai/api/v1'}
                />
              </div>
            )}
            <div className="col-span-full">
              <button type="submit" className="btn-primary text-sm" disabled={savingAi}>
                {savingAi ? 'Saving…' : savedAi ? 'Saved ✓' : 'Save AI Settings'}
              </button>
            </div>
          </form>
        </div>
      </section>

      {/* Integrations */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 mb-3">Integrations</h3>
        <div className="grid grid-cols-1 gap-4">
          {Object.keys(INTEGRATION_FIELDS).map((provider) => (
            <IntegrationSection
              key={provider}
              provider={provider}
              integration={intMap[provider] || null}
              onSave={saveIntegration}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
