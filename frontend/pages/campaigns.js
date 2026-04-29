import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';
import StatusBadge from '../components/StatusBadge';

const CAMPAIGN_STATUSES = ['draft', 'active', 'paused', 'completed', 'archived'];

const SERVICE_CATEGORIES = [
  'Peinture intérieure',
  'Réparation de gypse',
  'Escalier métallique extérieur',
  'Terrasse sablage et teinture',
  'Clôture',
  'Cuisine Ikea',
  'Peinture d\'armoires',
  'Petites rénovations',
  'Service homme à tout faire',
  'Préparation avant hiver',
  'Réparations extérieures',
];

const SEASONAL_PRESETS = [
  {
    name: 'Campagne printemps',
    service_category: 'Réparations extérieures',
    message: 'Profitez du printemps pour réparer, rénover et rafraîchir votre extérieur avec Bricopro.',
    status: 'draft',
  },
  {
    name: 'Campagne été — terrasses',
    service_category: 'Terrasse sablage et teinture',
    message: 'Redonnez vie à votre terrasse avec nos services de sablage et teinture professionnels.',
    status: 'draft',
  },
  {
    name: 'Préparation hiver',
    service_category: 'Préparation avant hiver',
    message: 'Préparez votre maison avant l\'hiver. Réparations extérieures, calfeutrage, toiture.',
    status: 'draft',
  },
  {
    name: 'Campagne hiver — intérieur',
    service_category: 'Peinture intérieure',
    message: 'L\'hiver est le bon moment pour les travaux intérieurs : peinture, gypse, rénovation cuisine.',
    status: 'draft',
  },
];

const EMPTY_FORM = {
  name: '', service_category: SERVICE_CATEGORIES[0], status: 'draft', message: '',
};

function CampaignCard({ campaign, onGenerate, onStatusChange, generatedDraftId }) {
  const [status, setStatus] = useState(campaign.status);

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-gray-800">{campaign.name}</h3>
          <p className="text-sm text-gray-500 mt-0.5">{campaign.service_category}</p>
        </div>
        <StatusBadge status={status} />
      </div>
      {campaign.message && (
        <p className="text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">{campaign.message}</p>
      )}
      <div className="flex flex-wrap gap-2 items-center mt-auto pt-2 border-t border-gray-50">
        <select
          className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white"
          value={status}
          onChange={(e) => { setStatus(e.target.value); onStatusChange(campaign.id, e.target.value); }}
        >
          {CAMPAIGN_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button
          className="btn-primary text-xs py-1.5 px-3"
          onClick={() => onGenerate(campaign.id)}
        >
          Generate Post
        </button>
        {generatedDraftId && (
          <span className="text-xs text-green-600 font-medium">
            Draft #{generatedDraftId} saved ✓
          </span>
        )}
      </div>
    </div>
  );
}

export default function CampaignsPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [campaigns, setCampaigns] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [generatedDrafts, setGeneratedDrafts] = useState({});

  const loadCampaigns = useCallback(async () => {
    const r = await apiFetch('/campaigns');
    if (r.ok) setCampaigns(await r.json());
  }, [apiFetch]);

  useEffect(() => { if (isLoggedIn) loadCampaigns(); }, [isLoggedIn]); // eslint-disable-line

  const createCampaign = async (e) => {
    e.preventDefault();
    setSaving(true);
    await apiFetch('/campaigns', { method: 'POST', body: JSON.stringify(form) });
    setSaving(false);
    setShowForm(false);
    setForm(EMPTY_FORM);
    await loadCampaigns();
  };

  const seedPreset = async (preset) => {
    await apiFetch('/campaigns', { method: 'POST', body: JSON.stringify(preset) });
    await loadCampaigns();
  };

  const generate = async (id) => {
    const r = await apiFetch(`/campaigns/${id}/generate`, { method: 'POST' });
    if (r.ok) {
      const data = await r.json();
      setGeneratedDrafts((p) => ({ ...p, [id]: data.draft_id }));
    }
  };

  const updateStatus = async (id, status) => {
    // Update in-memory optimistically; backend doesn't have PUT /campaigns/:id yet
    setCampaigns((prev) => prev.map((c) => c.id === id ? { ...c, status } : c));
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-2xl font-bold text-gray-900">Campaigns</h2>
        <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New Campaign'}
        </button>
      </div>
      <p className="text-gray-500 text-sm mb-6">Plan seasonal and service-based marketing campaigns.</p>

      {/* Create form */}
      {showForm && (
        <div className="card mb-6">
          <h3 className="font-semibold text-gray-800 mb-4">New Campaign</h3>
          <form onSubmit={createCampaign} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Campaign Name</label>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </div>
            <div>
              <label className="label">Service Category</label>
              <select className="select" value={form.service_category} onChange={(e) => setForm({ ...form, service_category: e.target.value })}>
                {SERVICE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Status</label>
              <select className="select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {CAMPAIGN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="col-span-full">
              <label className="label">Message / Focus</label>
              <textarea
                className="input h-20 resize-y"
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder="What is the key message for this campaign?"
              />
            </div>
            <div className="col-span-full flex gap-2">
              <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Create Campaign'}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Seasonal presets */}
      {campaigns.length === 0 && (
        <div className="card mb-6">
          <h3 className="font-semibold text-gray-800 mb-3">Start with a seasonal preset</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {SEASONAL_PRESETS.map((p) => (
              <button
                key={p.name}
                className="text-left p-3 rounded-lg border border-gray-200 hover:border-accent-400 hover:bg-accent-50 transition-colors"
                onClick={() => seedPreset(p)}
              >
                <p className="font-medium text-gray-800 text-sm">{p.name}</p>
                <p className="text-xs text-gray-500 mt-0.5">{p.service_category}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Campaign cards */}
      {campaigns.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {campaigns.map((c) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              onGenerate={generate}
              onStatusChange={updateStatus}
              generatedDraftId={generatedDrafts[c.id]}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-400 text-center py-8">
          No campaigns yet. Create one or pick a seasonal preset above.
        </p>
      )}
    </div>
  );
}
