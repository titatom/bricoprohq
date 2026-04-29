import Link from 'next/link';
import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

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

const PLATFORMS = [
  { value: 'facebook',   label: 'Facebook' },
  { value: 'instagram',  label: 'Instagram' },
  { value: 'gbp',        label: 'Google Business Profile' },
  { value: 'linkedin',   label: 'LinkedIn' },
  { value: 'website',    label: 'Website / Gallery' },
  { value: 'ad',         label: 'Ad concept' },
  { value: 'email_sms',  label: 'Email / SMS' },
];

const LANGUAGES = [
  { value: 'fr',        label: 'Français' },
  { value: 'en',        label: 'English' },
  { value: 'bilingual', label: 'Bilingual' },
];

const TONES = [
  { value: 'professional',  label: 'Professional' },
  { value: 'friendly',      label: 'Friendly' },
  { value: 'local',         label: 'Local / Neighbourly' },
  { value: 'premium',       label: 'Premium' },
  { value: 'educational',   label: 'Educational' },
  { value: 'urgent',        label: 'Urgent / Seasonal' },
  { value: 'trust',         label: 'Trust-building' },
  { value: 'before_after',  label: 'Before / After Showcase' },
];

const CTAS = [
  { value: 'request_quote',   label: 'Request a quote' },
  { value: 'book_spring',     label: 'Book spring work' },
  { value: 'book_winter',     label: 'Book before winter' },
  { value: 'visit_website',   label: 'Visit website' },
  { value: 'call_message',    label: 'Call / message us' },
  { value: 'ask_availability',label: 'Ask about availability' },
  { value: 'leave_review',    label: 'Leave a review' },
  { value: 'see_projects',    label: 'See more projects' },
];

const DEFAULT_FORM = {
  album_id: 'album-exteriors',
  service_category: SERVICE_CATEGORIES[0],
  platform: 'facebook',
  language: 'fr',
  tone: 'professional',
  job_description: '',
  city: 'Montréal',
  cta: 'request_quote',
};

const SEASONAL_CAMPAIGN_IDEAS = [
  {
    title: 'Exterior painting summer booking',
    season: 'March / April',
    focus: 'Use exterior project photos to book summer painting and repair work early.',
    service_category: 'Réparations extérieures',
  },
  {
    title: 'Deck sanding and stain push',
    season: 'April / May',
    focus: 'Promote before/after deck transformations before patio season.',
    service_category: 'Terrasse sablage et teinture',
  },
  {
    title: 'Interior refresh during winter',
    season: 'November / January',
    focus: 'Use interior painting images when exterior work slows down.',
    service_category: 'Peinture intérieure',
  },
];

function CandidateCard({ candidate, selected, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`text-left rounded-2xl border p-4 transition-colors ${
        selected ? 'border-accent-500 bg-accent-50' : 'border-gray-100 bg-white hover:border-brand-200'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-gray-900">{candidate.title}</p>
          <p className="text-xs text-gray-500 mt-1">{candidate.service_category}</p>
        </div>
        <span className="badge bg-brand-100 text-brand-700">{candidate.score}%</span>
      </div>
      <p className="text-sm text-gray-600 mt-3">{candidate.reason}</p>
      <div className="flex flex-wrap gap-1.5 mt-3">
        {(candidate.labels || []).map((label) => (
          <span key={label} className="badge bg-gray-100 text-gray-600">{label}</span>
        ))}
      </div>
      {candidate.before_after_pair && (
        <p className="text-xs text-accent-700 font-medium mt-3">Before/after candidate available</p>
      )}
    </button>
  );
}

function ResultCard({ result, onSave, saving }) {
  const [editedDrafts, setEditedDrafts] = useState(result.drafts || []);

  const updateDraft = (idx, patch) => {
    setEditedDrafts((prev) => prev.map((draft, i) => (i === idx ? { ...draft, ...patch } : draft)));
  };

  return (
    <div className="card mt-6 border-l-4 border-accent-500">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-gray-800">Editable content pack</h3>
          <p className="text-xs text-gray-400">Every field below can be changed before saving.</p>
        </div>
        <button className="btn-primary" onClick={() => onSave(editedDrafts)} disabled={saving}>
          {saving ? 'Saving…' : 'Save to Publishing Queue'}
        </button>
      </div>
      <div className="space-y-5">
        {editedDrafts.map((draft, idx) => (
          <div key={`${draft.platform}-${idx}`} className="rounded-2xl border border-gray-100 p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="label">Title</label>
                <input className="input" value={draft.title || ''} onChange={(e) => updateDraft(idx, { title: e.target.value })} />
              </div>
              <div>
                <label className="label">Platform</label>
                <select className="select" value={draft.platform || 'facebook'} onChange={(e) => updateDraft(idx, { platform: e.target.value })}>
                  {PLATFORMS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Main Copy</label>
                <textarea className="input h-36 resize-y" value={draft.main_copy || ''} onChange={(e) => updateDraft(idx, { main_copy: e.target.value })} />
              </div>
              <div>
                <label className="label">Short Variation</label>
                <textarea className="input h-36 resize-y" value={draft.short_variation || ''} onChange={(e) => updateDraft(idx, { short_variation: e.target.value })} />
              </div>
              <div>
                <label className="label">Hashtags</label>
                <input className="input" value={draft.hashtags || ''} onChange={(e) => updateDraft(idx, { hashtags: e.target.value })} />
              </div>
              <div>
                <label className="label">Call to Action</label>
                <input className="input" value={draft.cta || ''} onChange={(e) => updateDraft(idx, { cta: e.target.value })} />
              </div>
              <div>
                <label className="label">Selected Assets</label>
                <textarea className="input h-20 resize-y" value={(draft.selected_assets || []).join(', ')} readOnly />
              </div>
              <div>
                <label className="label">Before / After Direction</label>
                <textarea className="input h-20 resize-y" value={draft.visual_direction || ''} onChange={(e) => updateDraft(idx, { visual_direction: e.target.value })} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SocialStudioPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [form, setForm] = useState(DEFAULT_FORM);
  const [albums, setAlbums] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [selectedAssets, setSelectedAssets] = useState([]);
  const [result, setResult] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [kpiSaving, setKpiSaving] = useState(false);
  const [error, setError] = useState('');
  const [kpiForm, setKpiForm] = useState({
    title: '', platform: 'facebook', post_url: '', campaign_name: '', spend: 0,
    impressions: 0, reach: 0, clicks: 0, leads: 0, messages: 0, calls: 0,
    engagement_rate: 0, notes: '',
  });

  const loadAlbums = useCallback(async () => {
    const r = await apiFetch('/social/albums');
    if (r.ok) {
      const data = await r.json();
      setAlbums(data);
      if (data.length && !form.album_id) setForm((prev) => ({ ...prev, album_id: data[0].id }));
    }
  }, [apiFetch, form.album_id]);

  const loadCampaigns = useCallback(async () => {
    const r = await apiFetch('/campaigns');
    if (r.ok) setCampaigns(await r.json());
  }, [apiFetch]);

  useEffect(() => {
    if (!isLoggedIn) return;
    loadAlbums();
    loadCampaigns();
  }, [isLoggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  const analyzeAlbum = async () => {
    setAnalyzing(true); setError(''); setResult(null);
    const r = await apiFetch('/social/analyze-album', {
      method: 'POST',
      body: JSON.stringify({ album_id: form.album_id, service_category: form.service_category }),
    });
    if (r.ok) {
      const data = await r.json();
      setCandidates(data.candidates || []);
      setSelectedAssets((data.candidates || []).slice(0, 2).map((c) => c.asset_id));
    } else {
      setError('Album analysis failed.');
    }
    setAnalyzing(false);
  };

  const generate = async (e) => {
    e.preventDefault();
    setGenerating(true); setError(''); setResult(null);
    const selected = candidates.filter((c) => selectedAssets.includes(c.asset_id));
    const r = await apiFetch('/social/generate-pack', {
      method: 'POST',
      body: JSON.stringify({
        album_id: form.album_id,
        asset_ids: selected.map((c) => c.asset_id),
        platforms: [form.platform],
        service_category: form.service_category,
        language: form.language,
        tone: form.tone,
        city: form.city,
        cta: form.cta,
        job_description: form.job_description || selected.map((c) => `${c.title}: ${c.reason}`).join('\n'),
      }),
    });
    if (r.ok) {
      const data = await r.json();
      setResult({
        drafts: (data.drafts || []).map((draft) => ({
          ...draft,
          visual_direction: draft.visual_direction || (
            selected.some((c) => c.before_after_pair)
              ? 'Create before/after image if the selected assets pair cleanly.'
              : 'Use the strongest single finished-work image.'
          ),
        })),
      });
    } else {
      let msg = 'Generation failed.';
      try { const d = await r.json(); msg = d.detail || msg; } catch {}
      if (r.status === 502) msg = `AI provider error: ${msg}`;
      if (r.status === 400) msg = `Configuration issue: ${msg}`;
      setError(msg);
    }
    setGenerating(false);
  };

  const saveDraft = async (drafts) => {
    setSaving(true);
    setError('');
    let savedAll = true;
    for (const draft of drafts) {
      const r = await apiFetch('/publishing/drafts', {
        method: 'POST',
        body: JSON.stringify({
          title: draft.title,
          platform: draft.platform || form.platform,
          language: form.language,
          tone: form.tone,
          service_category: form.service_category,
          body: draft.main_copy,
          short_body: draft.short_variation,
          hashtags: draft.hashtags,
          cta: draft.cta,
          status: 'draft_generated',
        }),
      });
      if (!r.ok) {
        setError('Saving draft failed. Please review the generated content and try again.');
        savedAll = false;
        break;
      }
    }
    setSaving(false);
    if (savedAll) setError('Drafts saved to the publishing queue.');
  };

  const createCampaign = async (idea) => {
    const r = await apiFetch('/campaigns', {
      method: 'POST',
      body: JSON.stringify({
        name: idea.title,
        service_category: idea.service_category,
        status: 'draft',
        message: idea.focus,
      }),
    });
    if (!r.ok) {
      setError('Creating campaign failed.');
      return;
    }
    await loadCampaigns();
  };

  const saveKpi = async (e) => {
    e.preventDefault();
    setKpiSaving(true);
    setError('');
    const r = await apiFetch('/kpi/records', { method: 'POST', body: JSON.stringify(kpiForm) });
    setKpiSaving(false);
    if (!r.ok) {
      setError('Saving KPI record failed.');
      return;
    }
    setKpiForm({
      title: '', platform: 'facebook', post_url: '', campaign_name: '', spend: 0,
      impressions: 0, reach: 0, clicks: 0, leads: 0, messages: 0, calls: 0,
      engagement_rate: 0, notes: '',
    });
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6 max-w-6xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-1">AI Social Studio</h2>
          <p className="text-gray-500 text-sm">
            Analyze Immich albums, pick social-worthy images, generate editable copy, plan campaigns, and track results.
          </p>
        </div>
        <Link href="/settings/social-studio" className="btn-secondary text-sm">Social Studio Settings</Link>
      </div>

      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <span>🖼️</span> 1. Analyze an Immich album
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="label">Immich Album</label>
            <select
              className="select"
              value={form.album_id}
              onChange={(e) => setForm({ ...form, album_id: e.target.value })}
            >
              {albums.map((album) => <option key={album.id} value={album.id}>{album.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Service Category</label>
            <select
              className="select"
              value={form.service_category}
              onChange={(e) => setForm({ ...form, service_category: e.target.value })}
            >
              {SERVICE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <button type="button" className="btn-primary w-full" onClick={analyzeAlbum} disabled={analyzing}>
              {analyzing ? 'Analyzing…' : 'Analyze Album'}
            </button>
          </div>
        </div>
      </div>

      {candidates.length > 0 && (
        <div className="card mt-6">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span>🎯</span> 2. Select best candidates
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {candidates.map((candidate) => (
              <CandidateCard
                key={candidate.asset_id}
                candidate={candidate}
                selected={selectedAssets.includes(candidate.asset_id)}
                onToggle={() => setSelectedAssets((prev) => (
                  prev.includes(candidate.asset_id)
                    ? prev.filter((id) => id !== candidate.asset_id)
                    : [...prev, candidate.asset_id]
                ))}
              />
            ))}
          </div>
        </div>
      )}

      <div className="card mt-6">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <span>✍️</span> 3. Generate platform copy
        </h3>
        <form onSubmit={generate} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Platform</label>
            <select
              className="select"
              value={form.platform}
              onChange={(e) => setForm({ ...form, platform: e.target.value })}
            >
              {PLATFORMS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Language</label>
            <select
              className="select"
              value={form.language}
              onChange={(e) => setForm({ ...form, language: e.target.value })}
            >
              {LANGUAGES.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Tone</label>
            <select
              className="select"
              value={form.tone}
              onChange={(e) => setForm({ ...form, tone: e.target.value })}
            >
              {TONES.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">City / Neighbourhood</label>
            <input
              className="input"
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
              placeholder="Montréal, Plateau-Mont-Royal…"
            />
          </div>
          <div>
            <label className="label">Call to Action</label>
            <select
              className="select"
              value={form.cta}
              onChange={(e) => setForm({ ...form, cta: e.target.value })}
            >
              {CTAS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div className="col-span-full">
            <label className="label">Job Description</label>
            <textarea
              className="input h-24 resize-y"
              value={form.job_description}
              onChange={(e) => setForm({ ...form, job_description: e.target.value })}
              placeholder="Brief description of the work done. E.g. Repainted salon walls in Benjamin Moore Swiss Coffee, fixed two small drywall cracks…"
            />
          </div>
          {error && <p className="col-span-full text-sm text-red-600">{error}</p>}
          <div className="col-span-full flex gap-3">
            <button type="submit" className="btn-primary" disabled={generating}>
              {generating ? 'Generating…' : 'Generate Content Pack'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setForm(DEFAULT_FORM)}
            >
              Reset
            </button>
          </div>
        </form>
      </div>

      {result && (
        <ResultCard result={result} form={form} onSave={saveDraft} saving={saving} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <div className="card">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span>🎯</span> Campaign suggestions
          </h3>
          <div className="space-y-3">
            {SEASONAL_CAMPAIGN_IDEAS.map((idea) => (
              <div key={idea.title} className="rounded-xl border border-gray-100 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900">{idea.title}</p>
                    <p className="text-xs text-accent-700 font-medium mt-1">{idea.season}</p>
                    <p className="text-sm text-gray-600 mt-2">{idea.focus}</p>
                  </div>
                  <button className="btn-secondary text-xs" onClick={() => createCampaign(idea)}>Add</button>
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-4">{campaigns.length} campaign{campaigns.length !== 1 ? 's' : ''} currently saved.</p>
        </div>

        <div className="card">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span>📈</span> Track post / ad KPI
          </h3>
          <form onSubmit={saveKpi} className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input className="input md:col-span-2" placeholder="Post or ad title" value={kpiForm.title} onChange={(e) => setKpiForm({ ...kpiForm, title: e.target.value })} required />
            <select className="select" value={kpiForm.platform} onChange={(e) => setKpiForm({ ...kpiForm, platform: e.target.value })}>
              {PLATFORMS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
            <input className="input" placeholder="Campaign name" value={kpiForm.campaign_name} onChange={(e) => setKpiForm({ ...kpiForm, campaign_name: e.target.value })} />
            <input className="input md:col-span-2" placeholder="Post/ad URL" value={kpiForm.post_url} onChange={(e) => setKpiForm({ ...kpiForm, post_url: e.target.value })} />
            {['spend', 'impressions', 'reach', 'clicks', 'leads', 'messages', 'calls', 'engagement_rate'].map((field) => (
              <input
                key={field}
                className="input"
                type="number"
                step={field === 'spend' || field === 'engagement_rate' ? '0.01' : '1'}
                placeholder={field.replace('_', ' ')}
                value={kpiForm[field]}
                onChange={(e) => setKpiForm({ ...kpiForm, [field]: Number(e.target.value) })}
              />
            ))}
            <textarea className="input md:col-span-2 h-20 resize-y" placeholder="Notes" value={kpiForm.notes} onChange={(e) => setKpiForm({ ...kpiForm, notes: e.target.value })} />
            <button type="submit" className="btn-primary md:col-span-2" disabled={kpiSaving}>
              {kpiSaving ? 'Saving…' : 'Save KPI record'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
