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
  { value: 'facebook', label: 'Facebook' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'gbp', label: 'Google Business Profile' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'website', label: 'Website / Gallery' },
  { value: 'ad', label: 'Ad concept' },
  { value: 'email_sms', label: 'Email / SMS' },
];

const LANGUAGES = [
  { value: 'fr', label: 'Français' },
  { value: 'en', label: 'English' },
  { value: 'bilingual', label: 'Bilingual' },
];

const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'local', label: 'Local / Neighbourly' },
  { value: 'premium', label: 'Premium' },
  { value: 'educational', label: 'Educational' },
  { value: 'urgent', label: 'Urgent / Seasonal' },
  { value: 'trust', label: 'Trust-building' },
  { value: 'before_after', label: 'Before / After Showcase' },
];

const CTAS = [
  { value: 'request_quote', label: 'Request a quote' },
  { value: 'book_spring', label: 'Book spring work' },
  { value: 'book_winter', label: 'Book before winter' },
  { value: 'visit_website', label: 'Visit website' },
  { value: 'call_message', label: 'Call / message us' },
  { value: 'ask_availability', label: 'Ask about availability' },
  { value: 'leave_review', label: 'Leave a review' },
  { value: 'see_projects', label: 'See more projects' },
];

const DEFAULT_FORM = {
  album_id: '',
  service_category: SERVICE_CATEGORIES[0],
  platforms: ['facebook', 'instagram', 'gbp'],
  language: 'fr',
  tone: 'local',
  job_description: '',
  city: 'Montréal',
  cta: 'request_quote',
  before_after_requested: false,
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

function platformDefaults(value = '') {
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return parsed.length ? parsed : DEFAULT_FORM.platforms;
}

function ImmichPickerThumbnail({ asset }) {
  const { apiFetch } = useAuth();
  const [src, setSrc] = useState('');
  const [failed, setFailed] = useState(false);
  const assetId = asset?.id;

  useEffect(() => {
    let objectUrl = '';
    let cancelled = false;

    async function loadThumbnail() {
      if (!assetId) return;
      setFailed(false);
      setSrc('');
      try {
        const response = await apiFetch(`/integrations/immich/assets/${encodeURIComponent(assetId)}/thumbnail`, {
          headers: {},
        });
        if (!response.ok) throw new Error('thumbnail failed');
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch (err) {
        if (!cancelled) setFailed(true);
      }
    }

    loadThumbnail();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiFetch, assetId]);

  if (src && !failed) {
    return <img src={src} alt={asset.filename || 'Immich asset'} className="w-full h-full object-cover group-hover:scale-105 transition-transform" loading="lazy" />;
  }

  return (
    <div className="w-full h-full flex items-center justify-center text-xs text-gray-400 p-3 text-center">
      {failed ? 'Preview unavailable' : asset.filename || 'Photo'}
    </div>
  );
}

function ImmichImageCard({ asset, selected, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`group text-left rounded-2xl border overflow-hidden bg-white transition-all ${
        selected ? 'border-accent-500 ring-2 ring-accent-100' : 'border-gray-100 hover:border-brand-200'
      }`}
    >
      <div className="aspect-square bg-gray-100 overflow-hidden">
        <ImmichPickerThumbnail asset={asset} />
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-gray-800 truncate">{asset.filename || 'Untitled photo'}</p>
          <span className={`w-5 h-5 rounded-full border flex items-center justify-center text-xs ${selected ? 'bg-accent-500 border-accent-500 text-white' : 'border-gray-200 text-transparent'}`}>✓</span>
        </div>
        {asset.created_at && <p className="text-xs text-gray-400 mt-1">{new Date(asset.created_at).toLocaleDateString()}</p>}
      </div>
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
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="font-semibold text-gray-800">4. Review generated posts</h3>
          <p className="text-xs text-gray-400">Edit each platform draft before saving to the publishing queue.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => onSave(editedDrafts)} disabled={saving}>
            {saving ? 'Saving...' : 'Save to Publishing Queue'}
          </button>
          <button className="btn-secondary" type="button" disabled title="Direct publishing will be enabled once platform publishing endpoints are connected.">
            Post directly
          </button>
        </div>
      </div>
      <div className="space-y-5">
        {editedDrafts.map((draft, idx) => (
          <div key={`${draft.platform}-${idx}`} className="rounded-2xl border border-gray-100 p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="badge bg-brand-100 text-brand-700">{draft.platform}</span>
              {draft.ai_used === false && <span className="badge bg-yellow-100 text-yellow-700">Template fallback</span>}
            </div>
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
                <label className="label">Main copy</label>
                <textarea className="input h-40 resize-y" value={draft.main_copy || ''} onChange={(e) => updateDraft(idx, { main_copy: e.target.value })} />
              </div>
              <div>
                <label className="label">Short variation</label>
                <textarea className="input h-40 resize-y" value={draft.short_variation || ''} onChange={(e) => updateDraft(idx, { short_variation: e.target.value })} />
              </div>
              <div>
                <label className="label">Hashtags</label>
                <input className="input" value={draft.hashtags || ''} onChange={(e) => updateDraft(idx, { hashtags: e.target.value })} />
              </div>
              <div>
                <label className="label">Call to action</label>
                <input className="input" value={draft.cta || ''} onChange={(e) => updateDraft(idx, { cta: e.target.value })} />
              </div>
              <div>
                <label className="label">Selected Immich assets</label>
                <textarea className="input h-20 resize-y" value={(draft.selected_assets || []).join(', ')} readOnly />
              </div>
              <div>
                <label className="label">Visual direction</label>
                <textarea className="input h-20 resize-y" value={draft.visual_direction || ''} onChange={(e) => updateDraft(idx, { visual_direction: e.target.value })} />
              </div>
            </div>
            {draft.notes && <p className="text-xs text-gray-400 mt-3">{draft.notes}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SocialStudioPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [form, setForm] = useState(DEFAULT_FORM);
  const [settings, setSettings] = useState({});
  const [albums, setAlbums] = useState([]);
  const [assets, setAssets] = useState([]);
  const [selectedAssets, setSelectedAssets] = useState([]);
  const [result, setResult] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [kpiSaving, setKpiSaving] = useState(false);
  const [error, setError] = useState('');
  const [kpiForm, setKpiForm] = useState({
    title: '', platform: 'facebook', post_url: '', campaign_name: '', spend: 0,
    impressions: 0, reach: 0, clicks: 0, leads: 0, messages: 0, calls: 0,
    engagement_rate: 0, notes: '',
  });

  const applySettings = (data) => {
    setSettings(data);
    setForm((prev) => ({
      ...prev,
      album_id: data.default_album_id || prev.album_id,
      platforms: platformDefaults(data.default_platforms),
      language: data.default_language || prev.language,
      tone: data.default_tone || prev.tone,
      city: data.default_city || prev.city,
      cta: data.default_cta || prev.cta,
      before_after_requested: data.before_after_enabled === 'true' ? prev.before_after_requested : false,
    }));
  };

  const loadSettings = useCallback(async () => {
    const r = await apiFetch('/social/settings');
    if (r.ok) applySettings(await r.json());
  }, [apiFetch]);

  const loadAlbums = useCallback(async () => {
    const r = await apiFetch('/social/albums');
    if (r.ok) {
      const data = await r.json();
      setAlbums(data);
      setForm((prev) => ({ ...prev, album_id: prev.album_id || data[0]?.id || '' }));
    }
  }, [apiFetch]);

  const loadCampaigns = useCallback(async () => {
    const r = await apiFetch('/campaigns');
    if (r.ok) setCampaigns(await r.json());
  }, [apiFetch]);

  useEffect(() => {
    if (!isLoggedIn) return;
    loadSettings();
    loadAlbums();
    loadCampaigns();
  }, [isLoggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadAlbumAssets = async () => {
    if (!form.album_id) {
      setError('Choose an Immich album first.');
      return;
    }
    setLoadingAssets(true);
    setError('');
    setResult(null);
    const r = await apiFetch(`/social/immich/albums/${encodeURIComponent(form.album_id)}/assets?limit=80`);
    setLoadingAssets(false);
    if (!r.ok) {
      let msg = 'Could not load Immich album photos. Check Social Studio settings and the Immich integration.';
      try { const data = await r.json(); msg = data.detail || msg; } catch {}
      setError(msg);
      setAssets([]);
      return;
    }
    const data = await r.json();
    setAssets(data.assets || []);
    setSelectedAssets([]);
  };

  const togglePlatform = (platform) => {
    setForm((prev) => {
      const hasPlatform = prev.platforms.includes(platform);
      const platforms = hasPlatform
        ? prev.platforms.filter((item) => item !== platform)
        : [...prev.platforms, platform];
      return { ...prev, platforms: platforms.length ? platforms : [platform] };
    });
  };

  const generate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    setError('');
    setResult(null);
    const selected = assets.filter((asset) => selectedAssets.includes(asset.id));
    const r = await apiFetch('/social/generate-pack', {
      method: 'POST',
      body: JSON.stringify({
        album_id: form.album_id,
        asset_ids: selected.map((asset) => asset.id),
        platforms: form.platforms,
        service_category: form.service_category,
        language: form.language,
        tone: form.tone,
        city: form.city,
        cta: form.cta,
        before_after_requested: form.before_after_requested,
        job_description: form.job_description || selected.map((asset) => asset.filename || asset.title).join('\n'),
      }),
    });
    setGenerating(false);
    if (r.ok) {
      setResult(await r.json());
      return;
    }
    let msg = 'Generation failed.';
    try { const data = await r.json(); msg = data.detail || msg; } catch {}
    setError(msg);
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
          platform: draft.platform,
          language: form.language,
          tone: form.tone,
          service_category: form.service_category,
          body: draft.main_copy,
          short_body: draft.short_variation,
          hashtags: draft.hashtags,
          cta: draft.cta,
          status: 'needs_review',
        }),
      });
      if (!r.ok) {
        savedAll = false;
        setError('Saving draft failed. Please review the generated content and try again.');
        break;
      }
    }
    setSaving(false);
    if (savedAll) setError('Drafts saved to the publishing queue for review.');
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
    <div className="p-6 max-w-7xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-1">AI Social Studio</h2>
          <p className="text-gray-500 text-sm">
            Pick project photos from Immich, choose post options, generate editable platform posts, then save or publish.
          </p>
        </div>
        <Link href="/settings/social-studio" className="btn-secondary text-sm">Social Studio Settings</Link>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-6">
          <div className="card">
            <h3 className="font-semibold text-gray-800 mb-4">1. Pick images from Immich</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <label className="label">Configured Immich album</label>
                <select className="select" value={form.album_id} onChange={(e) => setForm({ ...form, album_id: e.target.value })}>
                  <option value="">Choose album...</option>
                  {albums.map((album) => <option key={album.id} value={album.id}>{album.name} {album.asset_count ? `(${album.asset_count})` : ''}</option>)}
                </select>
                <p className="text-xs text-gray-400 mt-1">
                  Album source is configured in Social Studio settings. Photos shown here are unfiltered; you choose the best ones.
                </p>
              </div>
              <div className="flex items-end">
                <button className="btn-primary w-full" type="button" onClick={loadAlbumAssets} disabled={loadingAssets || !form.album_id}>
                  {loadingAssets ? 'Loading photos...' : 'Load Photos'}
                </button>
              </div>
            </div>
            {settings.image_picker_prompt && (
              <div className="mt-4 rounded-xl bg-brand-50 border border-brand-100 p-3 text-sm text-brand-700">
                {settings.image_picker_prompt}
              </div>
            )}
            {assets.length > 0 && (
              <div className="mt-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm text-gray-500">{selectedAssets.length} of {assets.length} photos selected</p>
                  <button className="btn-secondary text-xs py-1 px-3" type="button" onClick={() => setSelectedAssets([])}>Clear selection</button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                  {assets.map((asset) => (
                    <ImmichImageCard
                      key={asset.id}
                      asset={asset}
                      selected={selectedAssets.includes(asset.id)}
                      onToggle={() => setSelectedAssets((prev) => (
                        prev.includes(asset.id) ? prev.filter((id) => id !== asset.id) : [...prev, asset.id]
                      ))}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="font-semibold text-gray-800 mb-4">2. Choose post options</h3>
            <form onSubmit={generate} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="label">Service category</label>
                <select className="select" value={form.service_category} onChange={(e) => setForm({ ...form, service_category: e.target.value })}>
                  {SERVICE_CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Language</label>
                <select className="select" value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
                  {LANGUAGES.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Tone</label>
                <select className="select" value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })}>
                  {TONES.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <label className="label">City / neighbourhood</label>
                <input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
              </div>
              <div>
                <label className="label">Call to action</label>
                <select className="select" value={form.cta} onChange={(e) => setForm({ ...form, cta: e.target.value })}>
                  {CTAS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Before / after montage</label>
                <label className="flex items-center gap-2 h-11 rounded-lg border border-gray-200 px-3 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={form.before_after_requested}
                    disabled={settings.before_after_enabled === 'false'}
                    onChange={(e) => setForm({ ...form, before_after_requested: e.target.checked })}
                  />
                  Selected photos are before/after candidates
                </label>
              </div>
              <div className="md:col-span-2">
                <label className="label">Platforms</label>
                <div className="flex flex-wrap gap-2">
                  {PLATFORMS.filter((p) => ['facebook', 'instagram', 'gbp'].includes(p.value)).map(({ value, label }) => (
                    <button
                      type="button"
                      key={value}
                      onClick={() => togglePlatform(value)}
                      className={`px-3 py-2 rounded-lg border text-sm ${form.platforms.includes(value) ? 'bg-brand-600 border-brand-600 text-white' : 'bg-white border-gray-200 text-gray-600 hover:border-brand-200'}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="md:col-span-2">
                <label className="label">Short job description</label>
                <textarea
                  className="input h-28 resize-y"
                  value={form.job_description}
                  onChange={(e) => setForm({ ...form, job_description: e.target.value })}
                  placeholder="Example: Repainted salon walls, fixed two drywall cracks, cleaned trim, finished in a warm neutral colour..."
                />
              </div>
              {error && <p className="md:col-span-2 text-sm text-red-600">{error}</p>}
              <div className="md:col-span-2 flex gap-3">
                <button type="submit" className="btn-primary" disabled={generating || selectedAssets.length === 0}>
                  {generating ? 'Generating...' : '3. Generate posts'}
                </button>
                <button type="button" className="btn-secondary" onClick={() => setForm({ ...DEFAULT_FORM, album_id: form.album_id })}>Reset options</button>
              </div>
            </form>
          </div>

          {result && <ResultCard result={result} onSave={saveDraft} saving={saving} />}
        </div>

        <div className="space-y-6">
          <div className="card">
            <h3 className="font-semibold text-gray-800 mb-3">Workflow status</h3>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between"><span className="text-gray-500">Album</span><span className="font-medium text-gray-800">{form.album_id || 'Not selected'}</span></div>
              <div className="flex items-center justify-between"><span className="text-gray-500">Photos loaded</span><span className="font-medium text-gray-800">{assets.length}</span></div>
              <div className="flex items-center justify-between"><span className="text-gray-500">Photos selected</span><span className="font-medium text-gray-800">{selectedAssets.length}</span></div>
              <div className="flex items-center justify-between"><span className="text-gray-500">Platforms</span><span className="font-medium text-gray-800">{form.platforms.join(', ')}</span></div>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold text-gray-800 mb-4">Campaign suggestions</h3>
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
            <h3 className="font-semibold text-gray-800 mb-4">Track post / ad KPI</h3>
            <form onSubmit={saveKpi} className="grid grid-cols-1 gap-3">
              <input className="input" placeholder="Post or ad title" value={kpiForm.title} onChange={(e) => setKpiForm({ ...kpiForm, title: e.target.value })} required />
              <select className="select" value={kpiForm.platform} onChange={(e) => setKpiForm({ ...kpiForm, platform: e.target.value })}>
                {PLATFORMS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
              </select>
              <input className="input" placeholder="Campaign name" value={kpiForm.campaign_name} onChange={(e) => setKpiForm({ ...kpiForm, campaign_name: e.target.value })} />
              <input className="input" placeholder="Post/ad URL" value={kpiForm.post_url} onChange={(e) => setKpiForm({ ...kpiForm, post_url: e.target.value })} />
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
              <textarea className="input h-20 resize-y" placeholder="Notes" value={kpiForm.notes} onChange={(e) => setKpiForm({ ...kpiForm, notes: e.target.value })} />
              <button type="submit" className="btn-primary" disabled={kpiSaving}>
                {kpiSaving ? 'Saving...' : 'Save KPI record'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
