import Link from 'next/link';
import { useEffect, useState, useCallback } from 'react';
import Calendar from 'react-calendar';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';
import StatusBadge from '../components/StatusBadge';

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', color: 'bg-blue-600', activeText: 'text-white', icon: 'f' },
  { value: 'instagram', label: 'Instagram', color: 'bg-gradient-to-r from-purple-500 to-pink-500', activeText: 'text-white', icon: 'IG' },
  { value: 'gbp', label: 'Google Business', color: 'bg-green-600', activeText: 'text-white', icon: 'G' },
  { value: 'linkedin', label: 'LinkedIn', color: 'bg-blue-700', activeText: 'text-white', icon: 'in' },
  { value: 'website', label: 'Website / Gallery', color: 'bg-gray-700', activeText: 'text-white', icon: 'W' },
  { value: 'ad', label: 'Ad concept', color: 'bg-amber-600', activeText: 'text-white', icon: 'Ad' },
  { value: 'email_sms', label: 'Email / SMS', color: 'bg-teal-600', activeText: 'text-white', icon: '@' },
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
  service_category: '',
  platforms: ['facebook', 'instagram', 'gbp'],
  language: 'fr',
  tone: 'local',
  job_description: '',
  city: 'Montréal',
  cta: 'request_quote',
};

const SS_TABS = [
  { key: 'post', label: 'Post Generation' },
  { key: 'image', label: 'Image Generation' },
  { key: 'campaigns', label: 'Campaigns' },
  { key: 'publishing', label: 'Publishing Queue' },
];

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

// ── Publishing constants ──────────────────────────────────────────────────────

const DRAFT_STATUSES = [
  'idea', 'draft_generated', 'needs_images', 'needs_review', 'approved',
  'scheduled', 'posted', 'reuse_later', 'turn_into_ad', 'turn_into_page', 'archived',
];

const PUB_PLATFORMS = ['facebook', 'instagram', 'gbp', 'linkedin', 'website', 'ad', 'email_sms'];

const KANBAN_COLS = [
  { key: 'idea',            label: 'Idea',           color: 'bg-purple-50 border-purple-200', emptyHint: 'Capture new content ideas here.' },
  { key: 'draft_generated', label: 'Draft',          color: 'bg-yellow-50 border-yellow-200', emptyHint: 'Generate a post in the Post tab to get started.' },
  { key: 'needs_review',    label: 'Needs Review',   color: 'bg-orange-50 border-orange-200', emptyHint: 'Move drafts here when ready for review.' },
  { key: 'approved',        label: 'Approved',       color: 'bg-brand-50 border-brand-200',   emptyHint: 'Approved posts will appear here. Review drafts to approve them.' },
  { key: 'scheduled',       label: 'Scheduled',      color: 'bg-cyan-50 border-cyan-200',     emptyHint: 'Drag approved posts here and assign a date to schedule.' },
  { key: 'posted',          label: 'Posted',         color: 'bg-green-50 border-green-200',   emptyHint: 'Published posts will show up here.' },
];

// ── Campaign constants ────────────────────────────────────────────────────────

const CAMPAIGN_STATUSES = ['draft', 'active', 'paused', 'completed', 'archived'];

const SEASONAL_PRESETS = [
  { name: 'Campagne printemps', service_category: 'Réparations extérieures', message: 'Profitez du printemps pour réparer, rénover et rafraîchir votre extérieur avec Bricopro.', status: 'draft' },
  { name: 'Campagne été — terrasses', service_category: 'Terrasse sablage et teinture', message: 'Redonnez vie à votre terrasse avec nos services de sablage et teinture professionnels.', status: 'draft' },
  { name: 'Préparation hiver', service_category: 'Préparation avant hiver', message: "Préparez votre maison avant l'hiver. Réparations extérieures, calfeutrage, toiture.", status: 'draft' },
  { name: 'Campagne hiver — intérieur', service_category: 'Peinture intérieure', message: "L'hiver est le bon moment pour les travaux intérieurs : peinture, gypse, rénovation cuisine.", status: 'draft' },
];

function platformDefaults(value = '') {
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return parsed.length ? parsed : DEFAULT_FORM.platforms;
}

// ── Shared image components ───────────────────────────────────────────────────

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
      className={`group text-left rounded-xl border overflow-hidden bg-white transition-all ${
        selected ? 'border-accent-500 ring-2 ring-accent-100' : 'border-gray-100 hover:border-brand-200'
      }`}
    >
      <div className="aspect-square bg-gray-100 overflow-hidden">
        <ImmichPickerThumbnail asset={asset} />
      </div>
      <div className="px-2 py-1.5">
        <div className="flex items-center justify-between gap-1">
          <p className="text-xs font-medium text-gray-800 truncate">{asset.filename || 'Untitled photo'}</p>
          <span className={`w-4 h-4 flex-shrink-0 rounded-full border flex items-center justify-center text-[10px] ${selected ? 'bg-accent-500 border-accent-500 text-white' : 'border-gray-200 text-transparent'}`}>✓</span>
        </div>
      </div>
    </button>
  );
}

function SelectedAssetThumbnails({ assets, selectedAssets }) {
  if (!selectedAssets.length) return null;
  const selected = assets.filter((a) => selectedAssets.includes(a.id));
  if (!selected.length) return null;
  return (
    <div className="mt-3">
      <p className="text-xs text-gray-500 mb-2">{selected.length} photo{selected.length > 1 ? 's' : ''} selected for AI context</p>
      <div className="flex flex-wrap gap-1.5">
        {selected.map((asset) => (
          <div key={asset.id} className="w-12 h-12 rounded-lg overflow-hidden border border-brand-200 bg-gray-100">
            <ImmichPickerThumbnail asset={asset} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ImmichImagePicker({ albums, assets, selectedAssets, setSelectedAssets, loadAlbumAssets, loadingAssets, form, setForm, settings, error, setError }) {
  return (
    <div className="card">
      <h3 className="font-semibold text-gray-800 mb-1">Pick images from Immich</h3>
      <p className="text-xs text-gray-400 mb-4">Select photos to provide context for AI copy generation and to use in the post.</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <label className="label">Immich album</label>
          <select className="select" value={form.album_id} onChange={(e) => setForm({ ...form, album_id: e.target.value })}>
            <option value="">Choose album...</option>
            {albums.map((album) => <option key={album.id} value={album.id}>{album.name} {album.asset_count ? `(${album.asset_count})` : ''}</option>)}
          </select>
        </div>
        <div className="flex items-end">
          <button className="btn-primary w-full" type="button" onClick={loadAlbumAssets} disabled={loadingAssets || !form.album_id}>
            {loadingAssets ? 'Loading photos...' : 'Load Photos'}
          </button>
        </div>
      </div>
      {assets.length > 0 && (
        <div className="mt-5">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-gray-500">{selectedAssets.length} of {assets.length} photos selected</p>
            <button className="btn-secondary text-xs py-1 px-3" type="button" onClick={() => setSelectedAssets([])}>Clear selection</button>
          </div>
          <div className="max-h-[400px] overflow-y-auto rounded-xl border border-gray-100 p-2">
            <div className="grid grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-2">
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
        </div>
      )}
      <SelectedAssetThumbnails assets={assets} selectedAssets={selectedAssets} />
    </div>
  );
}

// ── Result card ───────────────────────────────────────────────────────────────

function ResultCard({ result, onSave, onSaveSingle, saving, assets, selectedAssets }) {
  const [editedDrafts, setEditedDrafts] = useState(result.drafts || []);

  const updateDraft = (idx, patch) => {
    setEditedDrafts((prev) => prev.map((draft, i) => (i === idx ? { ...draft, ...patch } : draft)));
  };

  const handleSaveSingle = async (idx, status) => {
    const ok = await onSaveSingle(editedDrafts[idx], status);
    if (ok) {
      setEditedDrafts((prev) => prev.filter((_, i) => i !== idx));
    }
  };

  const selectedPhotos = (assets || []).filter((a) => (selectedAssets || []).includes(a.id));

  if (editedDrafts.length === 0) {
    return (
      <div className="card mt-6 border-l-4 border-green-500">
        <div className="flex items-center gap-3 py-2">
          <span className="text-green-600 text-lg">&#10003;</span>
          <div>
            <h3 className="font-semibold text-gray-800">All posts saved</h3>
            <p className="text-xs text-gray-400">Every generated draft has been sent to the publishing queue. Generate new content or review the Publishing Queue tab.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card mt-6 border-l-4 border-accent-500">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="font-semibold text-gray-800">Review generated posts</h3>
          <p className="text-xs text-gray-400">Edit each platform draft before saving to the publishing queue. Saved posts are removed automatically.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => onSave(editedDrafts)} disabled={saving}>
            {saving ? 'Saving...' : `Save All to Queue (${editedDrafts.length})`}
          </button>
        </div>
      </div>

      {selectedPhotos.length > 0 && (
        <div className="mb-4 p-3 bg-gray-50 rounded-xl">
          <p className="text-xs text-gray-500 mb-2">Selected photos sent to AI for analysis</p>
          <div className="flex flex-wrap gap-2">
            {selectedPhotos.map((asset) => (
              <div key={asset.id} className="w-14 h-14 rounded-lg overflow-hidden border border-brand-200 bg-gray-100">
                <ImmichPickerThumbnail asset={asset} />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-5">
        {editedDrafts.map((draft, idx) => (
          <div key={`${draft.platform}-${idx}`} className="rounded-2xl border border-gray-100 p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="badge bg-brand-100 text-brand-700">{draft.platform}</span>
              <div className="flex items-center gap-2">
                {draft.ai_used === false && <span className="badge bg-yellow-100 text-yellow-700">Template fallback</span>}
              </div>
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
            </div>
            {draft.notes && <p className="text-xs text-gray-400 mt-3">{draft.notes}</p>}
            <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-gray-100">
              <button className="px-3 py-1.5 rounded-lg border border-purple-200 bg-purple-50 text-purple-700 text-xs font-medium hover:bg-purple-100 transition-colors" onClick={() => handleSaveSingle(idx, 'idea')} disabled={saving}>
                Save as Idea
              </button>
              <button className="px-3 py-1.5 rounded-lg border border-yellow-200 bg-yellow-50 text-yellow-700 text-xs font-medium hover:bg-yellow-100 transition-colors" onClick={() => handleSaveSingle(idx, 'draft_generated')} disabled={saving}>
                Save as Draft
              </button>
              <button className="px-3 py-1.5 rounded-lg border border-orange-200 bg-orange-50 text-orange-700 text-xs font-medium hover:bg-orange-100 transition-colors" onClick={() => handleSaveSingle(idx, 'needs_review')} disabled={saving}>
                Send to Review
              </button>
              <button className="px-3 py-1.5 rounded-lg border border-green-200 bg-green-50 text-green-700 text-xs font-medium hover:bg-green-100 transition-colors" onClick={() => handleSaveSingle(idx, 'approved')} disabled={saving}>
                Approve
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Post Generation Tab ───────────────────────────────────────────────────────

function PostGenerationTab({ form, setForm, settings, albums, assets, selectedAssets, setSelectedAssets, loadAlbumAssets, loadingAssets, generate, generating, result, saveDraft, saveSingleDraft, saving, error, setError }) {
  const togglePlatform = (platform) => {
    setForm((prev) => {
      const hasPlatform = prev.platforms.includes(platform);
      const platforms = hasPlatform
        ? prev.platforms.filter((item) => item !== platform)
        : [...prev.platforms, platform];
      return { ...prev, platforms: platforms.length ? platforms : [platform] };
    });
  };

  return (
    <div className="space-y-6">
      <ImmichImagePicker
        albums={albums}
        assets={assets}
        selectedAssets={selectedAssets}
        setSelectedAssets={setSelectedAssets}
        loadAlbumAssets={loadAlbumAssets}
        loadingAssets={loadingAssets}
        form={form}
        setForm={setForm}
        settings={settings}
        error={error}
        setError={setError}
      />

      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Post options</h3>
        <form onSubmit={generate} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Service category</label>
            <input
              className="input"
              value={form.service_category}
              onChange={(e) => setForm({ ...form, service_category: e.target.value })}
              placeholder="e.g. Peinture intérieure, Réparation de gypse..."
            />
            <p className="text-xs text-gray-400 mt-1">Describe the service — fed to the AI for copy generation.</p>
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

          <div className="md:col-span-2">
            <label className="label">Platforms</label>
            <div className="flex flex-wrap gap-2">
              {PLATFORMS.map(({ value, label, color, icon }) => {
                const active = form.platforms.includes(value);
                return (
                  <button
                    type="button"
                    key={value}
                    onClick={() => togglePlatform(value)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border-2 text-sm font-medium transition-all ${
                      active
                        ? `${color} ${active ? 'text-white' : ''} border-transparent shadow-sm`
                        : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <span className={`w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold ${
                      active ? 'bg-white/20 text-white' : 'bg-gray-100 text-gray-400'
                    }`}>{icon}</span>
                    {label}
                  </button>
                );
              })}
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
              {generating ? 'Generating...' : 'Generate Posts'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setForm({ ...DEFAULT_FORM, album_id: form.album_id })}>Reset options</button>
          </div>
        </form>
      </div>

      {result && <ResultCard result={result} onSave={saveDraft} onSaveSingle={saveSingleDraft} saving={saving} assets={assets} selectedAssets={selectedAssets} />}
    </div>
  );
}

// ── Image Generation Tab ──────────────────────────────────────────────────────

function ImageGenerationTab({ albums, settings, apiFetch }) {
  const [imgForm, setImgForm] = useState({ album_id: '', prompt: '', preset: '', size: '1024x1024', quality: 'auto', refine_prompt: true });
  const [assets, setAssets] = useState([]);
  const [selectedAssets, setSelectedAssets] = useState([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [presets, setPresets] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [editingPreset, setEditingPreset] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadAlbumId, setUploadAlbumId] = useState('');

  useEffect(() => {
    loadPresets();
  }, []); // eslint-disable-line

  const loadPresets = async () => {
    const r = await apiFetch('/social/image-presets');
    if (r.ok) setPresets(await r.json());
  };

  const savePresets = async (updated) => {
    setPresets(updated);
    await apiFetch('/social/image-presets', {
      method: 'PUT',
      body: JSON.stringify({ presets: updated }),
    });
  };

  const addPreset = () => {
    const newPreset = { id: `custom_${Date.now()}`, name: 'New Preset', prompt: '', editable: true };
    setEditingPreset(newPreset);
  };

  const saveEditingPreset = () => {
    if (!editingPreset) return;
    const existing = presets.findIndex((p) => p.id === editingPreset.id);
    const updated = existing >= 0
      ? presets.map((p) => p.id === editingPreset.id ? editingPreset : p)
      : [...presets, editingPreset];
    savePresets(updated);
    setEditingPreset(null);
  };

  const deletePreset = (id) => {
    savePresets(presets.filter((p) => p.id !== id));
  };

  const loadAlbumAssets = async () => {
    if (!imgForm.album_id) return;
    setLoadingAssets(true);
    setError('');
    const r = await apiFetch(`/social/immich/albums/${encodeURIComponent(imgForm.album_id)}/assets?limit=80`);
    setLoadingAssets(false);
    if (!r.ok) {
      setError('Could not load album photos.');
      setAssets([]);
      return;
    }
    const data = await r.json();
    setAssets(data.assets || []);
    setSelectedAssets([]);
  };

  const generateImage = async () => {
    setGenerating(true);
    setError('');
    setResult(null);
    setUploadResult(null);
    const r = await apiFetch('/social/generate-image-actual', {
      method: 'POST',
      body: JSON.stringify({
        prompt: imgForm.prompt,
        preset: imgForm.preset,
        asset_ids: selectedAssets,
        size: imgForm.size,
        quality: imgForm.quality,
        refine_prompt: imgForm.refine_prompt,
      }),
    });
    setGenerating(false);
    if (r.ok) {
      const data = await r.json();
      setResult(data);
      setUploadAlbumId(imgForm.album_id || '');
      return;
    }
    let msg = 'Image generation failed.';
    try {
      const data = await r.json();
      msg = data.detail || msg;
    } catch {
      try { const text = await r.text(); if (text) msg = text.slice(0, 300); } catch {}
    }
    setError(msg);
  };

  const uploadToImmich = async () => {
    if (!result?.image_id) return;
    setUploading(true);
    setUploadResult(null);
    const r = await apiFetch(`/social/generated-images/${result.image_id}/upload-to-immich`, {
      method: 'POST',
      body: JSON.stringify({
        album_id: uploadAlbumId,
        filename: `bricopro-generated-${result.image_id}.png`,
      }),
    });
    setUploading(false);
    if (r.ok) {
      setUploadResult(await r.json());
      return;
    }
    let msg = 'Upload to Immich failed.';
    try { const data = await r.json(); msg = data.detail || msg; } catch {}
    setError(msg);
  };

  return (
    <div className="space-y-6">
      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-1">Pick reference images</h3>
        <p className="text-xs text-gray-400 mb-4">Select photos to provide visual context for image generation.</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="label">Immich album</label>
            <select className="select" value={imgForm.album_id} onChange={(e) => setImgForm({ ...imgForm, album_id: e.target.value })}>
              <option value="">Choose album...</option>
              {albums.map((album) => <option key={album.id} value={album.id}>{album.name} {album.asset_count ? `(${album.asset_count})` : ''}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <button className="btn-primary w-full" type="button" onClick={loadAlbumAssets} disabled={loadingAssets || !imgForm.album_id}>
              {loadingAssets ? 'Loading...' : 'Load Photos'}
            </button>
          </div>
        </div>
        {assets.length > 0 && (
          <div className="mt-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm text-gray-500">{selectedAssets.length} of {assets.length} photos selected</p>
              <button className="btn-secondary text-xs py-1 px-3" type="button" onClick={() => setSelectedAssets([])}>Clear</button>
            </div>
            <div className="max-h-[400px] overflow-y-auto rounded-xl border border-gray-100 p-2">
              <div className="grid grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-2">
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
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Image prompt</h3>
        <div className="space-y-4">
          <div>
            <label className="label">Presets</label>
            <div className="flex flex-wrap gap-2 mb-3">
              {presets.map((preset) => (
                <div key={preset.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      setImgForm({ ...imgForm, preset: preset.id, prompt: preset.prompt });
                    }}
                    className={`px-3 py-2 rounded-lg border text-sm transition-all ${
                      imgForm.preset === preset.id
                        ? 'bg-accent-500 border-accent-500 text-white'
                        : 'bg-white border-gray-200 text-gray-600 hover:border-accent-200'
                    }`}
                  >
                    {preset.name}
                  </button>
                  {preset.editable && (
                    <button
                      type="button"
                      className="text-xs text-gray-400 hover:text-gray-600 px-1"
                      onClick={() => setEditingPreset({ ...preset })}
                      title="Edit preset"
                    >
                      ✎
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={addPreset}
                className="px-3 py-2 rounded-lg border border-dashed border-gray-300 text-sm text-gray-400 hover:border-gray-400 hover:text-gray-600"
              >
                + Add Preset
              </button>
            </div>

            {editingPreset && (
              <div className="rounded-xl border border-accent-200 bg-accent-50 p-4 space-y-3">
                <div>
                  <label className="label">Preset name</label>
                  <input className="input" value={editingPreset.name} onChange={(e) => setEditingPreset({ ...editingPreset, name: e.target.value })} />
                </div>
                <div>
                  <label className="label">Prompt template</label>
                  <textarea className="input h-24 resize-y" value={editingPreset.prompt} onChange={(e) => setEditingPreset({ ...editingPreset, prompt: e.target.value })} />
                </div>
                <div className="flex gap-2">
                  <button type="button" className="btn-primary text-sm" onClick={saveEditingPreset}>Save Preset</button>
                  <button type="button" className="btn-secondary text-sm" onClick={() => setEditingPreset(null)}>Cancel</button>
                  {presets.some((p) => p.id === editingPreset.id) && (
                    <button type="button" className="btn-secondary text-sm text-red-600 border-red-200 hover:bg-red-50" onClick={() => { deletePreset(editingPreset.id); setEditingPreset(null); }}>Delete</button>
                  )}
                </div>
              </div>
            )}
          </div>

          <div>
            <label className="label">Prompt</label>
            <textarea
              className="input h-32 resize-y"
              value={imgForm.prompt}
              onChange={(e) => setImgForm({ ...imgForm, prompt: e.target.value })}
              placeholder="Describe the image you want to generate..."
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="label">Size</label>
              <select className="select" value={imgForm.size} onChange={(e) => setImgForm({ ...imgForm, size: e.target.value })}>
                <option value="1024x1024">1024 x 1024 (Square)</option>
                <option value="1536x1024">1536 x 1024 (Landscape)</option>
                <option value="1024x1536">1024 x 1536 (Portrait)</option>
                <option value="auto">Auto</option>
              </select>
            </div>
            <div>
              <label className="label">Quality</label>
              <select className="select" value={imgForm.quality} onChange={(e) => setImgForm({ ...imgForm, quality: e.target.value })}>
                <option value="auto">Auto</option>
                <option value="low">Low</option>
                <option value="standard">Standard</option>
                <option value="high">High</option>
                <option value="hd">HD</option>
              </select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={imgForm.refine_prompt}
                  onChange={(e) => setImgForm({ ...imgForm, refine_prompt: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-accent-500 focus:ring-accent-500"
                />
                <span className="text-sm text-gray-700">Refine prompt with AI first</span>
              </label>
            </div>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="button"
            className="btn-primary"
            onClick={generateImage}
            disabled={generating || (!imgForm.prompt && !imgForm.preset)}
          >
            {generating ? 'Generating image...' : 'Generate Image'}
          </button>
          {generating && (
            <p className="text-xs text-gray-400 mt-1">Image generation can take 15-60 seconds depending on the model and settings.</p>
          )}
        </div>
      </div>

      {result && (
        <div className="card border-l-4 border-accent-500">
          <h3 className="font-semibold text-gray-800 mb-3">Generated Image</h3>
          <div className="space-y-4">
            <div className="rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
              <img
                src={result.image_data_url || result.image_url}
                alt="Generated image"
                className="w-full max-w-2xl mx-auto block"
                style={{ aspectRatio: (imgForm.size === '1792x1024' || imgForm.size === '1536x1024') ? '3/2' : (imgForm.size === '1024x1792' || imgForm.size === '1024x1536') ? '2/3' : '1/1' }}
              />
            </div>

            {result.revised_prompt && (
              <div>
                <label className="label">Prompt used by the model</label>
                <textarea className="input h-24 resize-y text-sm" value={result.revised_prompt} readOnly />
              </div>
            )}

            {result.refined_prompt && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="label">Suggested style</label>
                  <input className="input" value={result.refined_prompt?.style || ''} readOnly />
                </div>
                <div>
                  <label className="label">Aspect ratio</label>
                  <input className="input" value={result.refined_prompt?.aspect_ratio || ''} readOnly />
                </div>
                <div>
                  <label className="label">Notes</label>
                  <input className="input" value={result.refined_prompt?.notes || ''} readOnly />
                </div>
              </div>
            )}

            <div className="border-t border-gray-100 pt-4">
              <h4 className="font-medium text-gray-700 mb-3">Send to Immich</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                <div className="md:col-span-2">
                  <label className="label">Destination album</label>
                  <select className="select" value={uploadAlbumId} onChange={(e) => setUploadAlbumId(e.target.value)}>
                    <option value="">No album (upload to library only)</option>
                    {albums.map((album) => <option key={album.id} value={album.id}>{album.name} {album.asset_count ? `(${album.asset_count})` : ''}</option>)}
                  </select>
                </div>
                <div>
                  <button
                    type="button"
                    className="btn-primary w-full"
                    onClick={uploadToImmich}
                    disabled={uploading}
                  >
                    {uploading ? 'Uploading...' : 'Upload to Immich'}
                  </button>
                </div>
              </div>
              {uploadResult && (
                <div className="mt-3 rounded-lg bg-green-50 border border-green-200 p-3">
                  <p className="text-sm text-green-700 font-medium">
                    Image uploaded successfully to Immich{uploadResult.album_id ? ' and added to album' : ''}.
                  </p>
                  <p className="text-xs text-green-600 mt-1">Asset ID: {uploadResult.asset_id}</p>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span>Model: {result.model}</span>
              <span>|</span>
              <span>Size: {result.size}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Campaigns Tab ─────────────────────────────────────────────────────────────

function CampaignsTab({ apiFetch }) {
  const [campaigns, setCampaigns] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', service_category: '', status: 'draft', message: '' });
  const [saving, setSaving] = useState(false);
  const [generatedDrafts, setGeneratedDrafts] = useState({});

  const loadCampaigns = useCallback(async () => {
    const r = await apiFetch('/campaigns');
    if (r.ok) setCampaigns(await r.json());
  }, [apiFetch]);

  useEffect(() => { loadCampaigns(); }, []); // eslint-disable-line

  const createCampaign = async (e) => {
    e.preventDefault();
    setSaving(true);
    await apiFetch('/campaigns', { method: 'POST', body: JSON.stringify(form) });
    setSaving(false);
    setShowForm(false);
    setForm({ name: '', service_category: '', status: 'draft', message: '' });
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

  const updateStatus = async (id, newStatus) => {
    const campaign = campaigns.find((c) => c.id === id);
    setCampaigns((prev) => prev.map((c) => c.id === id ? { ...c, status: newStatus } : c));
    if (campaign) {
      await apiFetch(`/campaigns/${id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: campaign.name,
          service_category: campaign.service_category || '',
          message: campaign.message || '',
          status: newStatus,
        }),
      });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-800">Campaigns</h3>
          <p className="text-sm text-gray-500 mt-0.5">Plan seasonal and service-based marketing campaigns.</p>
        </div>
        <button className="btn-primary text-sm" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New Campaign'}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3 className="font-semibold text-gray-800 mb-4">New Campaign</h3>
          <form onSubmit={createCampaign} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Campaign Name</label>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </div>
            <div>
              <label className="label">Service Category</label>
              <input className="input" value={form.service_category} onChange={(e) => setForm({ ...form, service_category: e.target.value })} placeholder="e.g. Peinture intérieure" />
            </div>
            <div>
              <label className="label">Status</label>
              <select className="select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {CAMPAIGN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="col-span-full">
              <label className="label">Message / Focus</label>
              <textarea className="input h-20 resize-y" value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} placeholder="What is the key message for this campaign?" />
            </div>
            <div className="col-span-full flex gap-2">
              <button type="submit" className="btn-primary text-sm" disabled={saving}>{saving ? 'Saving…' : 'Create Campaign'}</button>
              <button type="button" className="btn-secondary text-sm" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {campaigns.length === 0 && (
        <div className="card">
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

      {campaigns.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {campaigns.map((c) => (
            <div key={c.id} className="card flex flex-col gap-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-800">{c.name}</h3>
                  <p className="text-sm text-gray-500 mt-0.5">{c.service_category}</p>
                </div>
                <StatusBadge status={c.status} />
              </div>
              {c.message && <p className="text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">{c.message}</p>}
              <div className="flex flex-wrap gap-2 items-center mt-auto pt-2 border-t border-gray-50">
                <select
                  className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white"
                  value={c.status}
                  onChange={(e) => updateStatus(c.id, e.target.value)}
                >
                  {CAMPAIGN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <button className="btn-primary text-xs py-1.5 px-3" onClick={() => generate(c.id)}>Generate Post</button>
                {generatedDrafts[c.id] && <span className="text-xs text-green-600 font-medium">Draft #{generatedDrafts[c.id]} saved</span>}
              </div>
            </div>
          ))}
        </div>
      )}

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
                <button className="btn-secondary text-xs" onClick={() => seedPreset({ name: idea.title, service_category: idea.service_category, message: idea.focus, status: 'draft' })}>Add</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Publishing Queue Tab ──────────────────────────────────────────────────────

const PLATFORM_CHAR_LIMITS = {
  facebook: 63206,
  instagram: 2200,
  gbp: 1500,
  linkedin: 3000,
  website: 10000,
  ad: 500,
  email_sms: 480,
};

function CharCount({ text, platform }) {
  const len = (text || '').length;
  const limit = PLATFORM_CHAR_LIMITS[platform];
  if (!limit) return <span className="text-xs text-gray-400">{len} chars</span>;
  const pct = len / limit;
  const color = pct > 1 ? 'text-red-600 font-medium' : pct > 0.9 ? 'text-amber-600' : 'text-gray-400';
  return <span className={`text-xs ${color}`}>{len} / {limit.toLocaleString()}</span>;
}

function copyDraftToClipboard(d) {
  const parts = [d.body || d.main_copy || '', d.hashtags, d.cta].filter(Boolean);
  const text = parts.join('\n\n');
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {});
    return true;
  }
  return false;
}

const PLATFORM_ICONS = {
  facebook: { label: 'Facebook', color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
  instagram: { label: 'Instagram', color: 'text-pink-600', bg: 'bg-pink-50 border-pink-200' },
  gbp: { label: 'Google Business', color: 'text-green-700', bg: 'bg-green-50 border-green-200' },
  linkedin: { label: 'LinkedIn', color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200' },
};

function PublishPanel({ draft, apiFetch, onSuccess }) {
  const [accounts, setAccounts] = useState([]);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [publishing, setPublishing] = useState(false);
  const [scheduleMode, setScheduleMode] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoadingAccounts(true);
    apiFetch('/publishing/accounts').then(async (r) => {
      if (r.ok) {
        const all = await r.json();
        // Filter accounts to match this draft's platform
        const platformMap = { facebook: 'facebook_page', instagram: 'instagram', gbp: 'gbp_location' };
        const filtered = all.filter((a) => a.type === platformMap[draft.platform]) || all;
        setAccounts(filtered.length ? filtered : all);
        if (filtered.length === 1) setSelectedAccount(filtered[0].account_id);
      }
      setLoadingAccounts(false);
    }).catch(() => setLoadingAccounts(false));
  }, [draft.platform]); // eslint-disable-line

  const isInstagram = draft.platform === 'instagram';
  const imageIds = (draft.image_ids || '').split(',').filter(Boolean);
  const hasImages = imageIds.length > 0;

  const doPublish = async () => {
    if (!selectedAccount) { setError('Please select an account.'); return; }
    if (isInstagram && !hasImages) { setError('Instagram requires at least one image. Add images to this draft first.'); return; }
    setPublishing(true);
    setError('');
    const r = await apiFetch(`/publishing/drafts/${draft.id}/publish`, {
      method: 'POST',
      body: JSON.stringify({ platform_account_id: selectedAccount, schedule: scheduleMode }),
    });
    setPublishing(false);
    if (r.ok) {
      const data = await r.json();
      setResult(data);
      if (onSuccess) onSuccess();
    } else {
      const err = await r.json().catch(() => ({}));
      setError(err.detail || 'Publish failed. Check your connection and try again.');
    }
  };

  if (result) {
    return (
      <div className="rounded-xl bg-green-50 border border-green-200 p-4 space-y-2">
        <p className="font-semibold text-green-800 text-sm">
          {result.scheduled ? 'Scheduled successfully!' : 'Published successfully!'}
        </p>
        {result.platform_post_id && (
          <p className="text-xs text-green-700">Post ID: <span className="font-mono">{result.platform_post_id}</span></p>
        )}
        {result.published_at && (
          <p className="text-xs text-green-600">Published at: {new Date(result.published_at).toLocaleString()}</p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-gray-50 border border-gray-200 p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-800">Publish to {PLATFORM_ICONS[draft.platform]?.label || draft.platform}</p>

      {loadingAccounts ? (
        <p className="text-xs text-gray-400">Loading connected accounts…</p>
      ) : accounts.length === 0 ? (
        <p className="text-xs text-red-500">No {draft.platform} accounts connected. Check Settings → Integrations.</p>
      ) : (
        <div>
          <label className="label text-xs">Account / Page</label>
          <select className="select text-sm" value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)}>
            <option value="">Select account…</option>
            {accounts.map((a) => <option key={a.account_id} value={a.account_id}>{a.account_name}</option>)}
          </select>
        </div>
      )}

      {isInstagram && !hasImages && (
        <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          Instagram requires at least one image. Add images to this draft before publishing.
        </p>
      )}

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            className="rounded border-gray-300"
            checked={scheduleMode}
            onChange={(e) => setScheduleMode(e.target.checked)}
          />
          Schedule for planned date/time
        </label>
      </div>

      {scheduleMode && (!draft.planned_date || !draft.planned_time) && (
        <p className="text-xs text-amber-600">Set a planned date and time above before scheduling.</p>
      )}

      {error && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">{error}</p>}

      <button
        className="btn-primary w-full text-sm py-2"
        onClick={doPublish}
        disabled={publishing || loadingAccounts || accounts.length === 0}
      >
        {publishing ? 'Publishing…' : scheduleMode ? 'Schedule Post' : 'Publish Now'}
      </button>
    </div>
  );
}

function DraftModal({ draft, onClose, onStatusChange, onDelete, onUpdate, apiFetch }) {
  const [status, setStatus] = useState(draft.status);
  const [title, setTitle] = useState(draft.title || '');
  const [body, setBody] = useState(draft.body || '');
  const [shortBody, setShortBody] = useState(draft.short_body || '');
  const [hashtags, setHashtags] = useState(draft.hashtags || '');
  const [cta, setCta] = useState(draft.cta || '');
  const [plannedDate, setPlannedDate] = useState(draft.planned_date || '');
  const [plannedTime, setPlannedTime] = useState(draft.planned_time || '');
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showPublish, setShowPublish] = useState(false);

  const imageIdList = (draft.image_ids || '').split(',').filter(Boolean);
  const isPublishable = ['facebook', 'instagram', 'gbp'].includes(draft.platform);
  const isAlreadyPublished = !!draft.platform_post_id;

  const saveAll = async () => {
    setSaving(true);
    setFeedback('');
    const r = await apiFetch(`/publishing/drafts/${draft.id}`, {
      method: 'PUT',
      body: JSON.stringify({ title, body, short_body: shortBody, hashtags, cta, planned_date: plannedDate || null, planned_time: plannedTime, status }),
    });
    setSaving(false);
    if (r.ok) {
      setFeedback('Draft saved.');
      if (onUpdate) onUpdate();
    } else {
      setFeedback('Save failed.');
    }
  };

  const handleDelete = async () => {
    setSaving(true);
    await onDelete(draft.id);
    setSaving(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="font-semibold text-gray-900 text-lg">Edit Draft</h3>
            {isAlreadyPublished && (
              <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5 mt-1">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
                Live · {draft.platform_post_id}
              </span>
            )}
            {draft.publish_error && (
              <span className="inline-flex items-center gap-1 text-xs text-red-600 bg-red-50 border border-red-200 rounded-full px-2 py-0.5 mt-1">
                Failed: {draft.publish_error.slice(0, 60)}
              </span>
            )}
          </div>
          <button className="text-gray-400 hover:text-gray-600 text-xl leading-none" onClick={onClose}>×</button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Title</label>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <label className="label">Platform</label>
              <select className="select" value={draft.platform} disabled>
                {PLATFORMS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="label">Main copy</label>
              <CharCount text={body} platform={draft.platform} />
            </div>
            <textarea className="input h-32 resize-y" value={body} onChange={(e) => setBody(e.target.value)} />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="label">Short variation</label>
              <span className="text-xs text-gray-400">{(shortBody || '').length} chars</span>
            </div>
            <textarea className="input h-20 resize-y" value={shortBody} onChange={(e) => setShortBody(e.target.value)} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Hashtags</label>
              <input className="input" value={hashtags} onChange={(e) => setHashtags(e.target.value)} />
            </div>
            <div>
              <label className="label">Call to action</label>
              <input className="input" value={cta} onChange={(e) => setCta(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="label">Scheduled date</label>
              <input className="input" type="date" value={plannedDate} onChange={(e) => setPlannedDate(e.target.value)} />
            </div>
            <div>
              <label className="label">Time</label>
              <input className="input" type="time" value={plannedTime} onChange={(e) => setPlannedTime(e.target.value)} />
            </div>
            <div>
              <label className="label">Status</label>
              <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
                {DRAFT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
          </div>

          {imageIdList.length > 0 && (
            <div>
              <label className="label">Attached images</label>
              <div className="flex flex-wrap gap-1.5">
                {imageIdList.map((assetId) => (
                  <div key={assetId} className="w-12 h-12 rounded-lg overflow-hidden border border-brand-200 bg-gray-100">
                    <ImmichPickerThumbnail asset={{ id: assetId }} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {isPublishable && showPublish && (
            <PublishPanel
              draft={{ ...draft, planned_date: plannedDate, planned_time: plannedTime, body, hashtags, cta }}
              apiFetch={apiFetch}
              onSuccess={() => { if (onUpdate) onUpdate(); }}
            />
          )}

          {draft.campaign_id && <p className="text-sm text-gray-500">Campaign: #{draft.campaign_id}</p>}
          {feedback && <p className="text-sm text-green-600 font-medium">{feedback}</p>}
        </div>

        <div className="flex flex-wrap gap-2 justify-between mt-6 pt-4 border-t border-gray-100">
          <div className="flex flex-wrap gap-2">
            <button
              className="px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-700 text-sm font-medium hover:bg-gray-100 transition-colors"
              onClick={() => { if (copyDraftToClipboard({ body, hashtags, cta })) { setCopied(true); setTimeout(() => setCopied(false), 2000); } }}
            >
              {copied ? 'Copied!' : 'Copy to Clipboard'}
            </button>
            {isPublishable && !isAlreadyPublished && (
              <button
                className="px-3 py-2 rounded-lg border border-brand-300 bg-brand-50 text-brand-700 text-sm font-semibold hover:bg-brand-100 transition-colors"
                onClick={() => setShowPublish((v) => !v)}
                disabled={saving}
              >
                {showPublish ? 'Hide Publish' : 'Publish / Schedule'}
              </button>
            )}
            {confirmDelete ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-red-600">Delete this draft?</span>
                <button className="px-3 py-2 rounded-lg border border-red-300 bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors" onClick={handleDelete} disabled={saving}>
                  Confirm
                </button>
                <button className="px-2 py-2 text-xs text-gray-500 hover:text-gray-700" onClick={() => setConfirmDelete(false)}>Cancel</button>
              </div>
            ) : (
              <button className="px-3 py-2 rounded-lg border border-red-200 bg-red-50 text-red-600 text-sm font-medium hover:bg-red-100 transition-colors" onClick={() => setConfirmDelete(true)} disabled={saving}>
                Delete
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={onClose}>Close</button>
            <button className="btn-primary" onClick={saveAll} disabled={saving}>
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function KanbanBoard({ drafts, onStatusChange, onDelete, onUpdate, apiFetch }) {
  const [selected, setSelected] = useState(null);
  const [dragOverCol, setDragOverCol] = useState(null);
  const grouped = {};
  KANBAN_COLS.forEach(({ key }) => { grouped[key] = []; });
  drafts.forEach((d) => {
    if (grouped[d.status]) grouped[d.status].push(d);
    else { grouped['draft_generated'] = grouped['draft_generated'] || []; grouped['draft_generated'].push(d); }
  });

  const handleDragStart = (e, draft) => {
    e.dataTransfer.setData('text/plain', JSON.stringify({ id: draft.id, status: draft.status }));
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e, colKey) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverCol(colKey);
  };

  const handleDragLeave = () => {
    setDragOverCol(null);
  };

  const handleDrop = async (e, targetStatus) => {
    e.preventDefault();
    setDragOverCol(null);
    try {
      const data = JSON.parse(e.dataTransfer.getData('text/plain'));
      if (data.id && data.status !== targetStatus) {
        await onStatusChange(data.id, targetStatus);
      }
    } catch {}
  };

  return (
    <>
      {selected && <DraftModal draft={selected} onClose={() => { setSelected(null); if (onUpdate) onUpdate(); }} onStatusChange={onStatusChange} onDelete={onDelete} onUpdate={onUpdate} apiFetch={apiFetch} />}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {KANBAN_COLS.map(({ key, label, color, emptyHint }) => (
          <div
            key={key}
            className={`flex-shrink-0 w-56 rounded-xl border p-3 transition-colors ${color} ${dragOverCol === key ? 'ring-2 ring-brand-400 ring-offset-1' : ''}`}
            onDragOver={(e) => handleDragOver(e, key)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, key)}
          >
            <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-3">
              {label} <span className="text-gray-400 font-normal">({grouped[key]?.length || 0})</span>
            </p>
            <div className="space-y-2">
              {(grouped[key] || []).map((d) => (
                <div
                  key={d.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, d)}
                  className="bg-white rounded-lg p-3 shadow-sm cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow border border-gray-100"
                  onClick={() => setSelected(d)}
                >
                  <div className="flex items-start justify-between gap-1">
                    <p className="text-sm font-medium text-gray-800 truncate">{d.title}</p>
                    {d.platform_post_id && (
                      <span className="flex-shrink-0 w-2 h-2 rounded-full bg-green-500 mt-1" title="Published — live on platform" />
                    )}
                    {d.status === 'failed' && (
                      <span className="flex-shrink-0 w-2 h-2 rounded-full bg-red-500 mt-1" title={d.publish_error || 'Publish failed'} />
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="text-xs text-gray-400">{d.platform}</span>
                    {d.planned_date && <span className="text-xs text-gray-400">· {d.planned_date}{d.planned_time ? ` ${d.planned_time}` : ''}</span>}
                    {d.image_ids && <span className="inline-flex items-center gap-0.5 text-[10px] text-brand-500 bg-brand-50 rounded px-1">IMG {d.image_ids.split(',').filter(Boolean).length}</span>}
                  </div>
                </div>
              ))}
              {(!grouped[key] || grouped[key].length === 0) && (
                <div className="text-center py-4 px-2">
                  <p className="text-xs text-gray-400 italic">{emptyHint}</p>
                  <p className="text-[10px] text-gray-300 mt-1">Drag &amp; drop cards here</p>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function CalendarView({ drafts }) {
  const [selectedDate, setSelectedDate] = useState(null);

  const byDate = {};
  drafts.forEach((d) => {
    const key = d.date || d.planned_date;
    if (key) { byDate[key] = byDate[key] || []; byDate[key].push(d); }
  });

  const toDateStr = (d) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const tileContent = ({ date, view }) => {
    if (view !== 'month') return null;
    const key = toDateStr(date);
    const items = byDate[key];
    if (!items || items.length === 0) return null;
    return (
      <div className="flex flex-wrap gap-0.5 justify-center mt-0.5">
        {items.slice(0, 3).map((d) => (
          <span key={d.id} className="w-1.5 h-1.5 rounded-full bg-brand-500 inline-block" />
        ))}
        {items.length > 3 && <span className="text-[9px] text-brand-500 leading-none">+{items.length - 3}</span>}
      </div>
    );
  };

  const tileClassName = ({ date, view }) => {
    if (view !== 'month') return '';
    const key = toDateStr(date);
    return byDate[key] ? 'has-drafts' : '';
  };

  const handleDayClick = (date) => {
    const key = toDateStr(date);
    setSelectedDate(byDate[key] ? key : null);
  };

  const selectedDrafts = selectedDate ? (byDate[selectedDate] || []) : [];

  return (
    <div>
      <style>{`
        .pub-calendar .react-calendar { width: 100%; border: none; font-family: inherit; }
        .pub-calendar .react-calendar__tile { padding: 0.5em 0.25em; font-size: 0.8rem; border-radius: 0.5rem; min-height: 3.5rem; }
        .pub-calendar .react-calendar__tile:hover { background: #f3f4f6; }
        .pub-calendar .react-calendar__tile--active { background: #e0e7ff !important; color: #3730a3; }
        .pub-calendar .react-calendar__tile.has-drafts { background: #eff6ff; font-weight: 600; }
        .pub-calendar .react-calendar__navigation button { font-size: 0.9rem; font-weight: 600; padding: 0.5rem; border-radius: 0.5rem; }
        .pub-calendar .react-calendar__navigation button:hover { background: #f3f4f6; }
        .pub-calendar .react-calendar__month-view__weekdays { font-size: 0.7rem; text-transform: uppercase; color: #9ca3af; }
        .pub-calendar .react-calendar__month-view__weekdays abbr { text-decoration: none; }
      `}</style>
      <div className="pub-calendar">
        <Calendar
          onClickDay={handleDayClick}
          tileContent={tileContent}
          tileClassName={tileClassName}
          locale="en-US"
        />
      </div>
      {selectedDate && (
        <div className="mt-4 border-t border-gray-100 pt-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">{selectedDate}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {selectedDrafts.map((d) => (
              <div key={d.id} className="bg-white border border-gray-100 rounded-lg p-3 shadow-sm">
                <p className="text-sm font-medium text-gray-800 truncate">{d.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="badge bg-gray-100 text-gray-600">{d.platform}</span>
                  {(d.planned_time) && <span className="text-xs text-gray-400">{d.planned_time}</span>}
                  <StatusBadge status={d.status} />
                  {d.image_ids && <span className="text-[10px] text-brand-500 bg-brand-50 rounded px-1">IMG</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {!selectedDate && Object.keys(byDate).length === 0 && (
        <p className="text-sm text-gray-400 py-4 text-center">No posts scheduled yet. Assign a planned date to drafts.</p>
      )}
      {!selectedDate && Object.keys(byDate).length > 0 && (
        <p className="text-sm text-gray-400 py-3 text-center">Click a date to see scheduled posts.</p>
      )}
    </div>
  );
}

function InlineEditableTitle({ draft, apiFetch, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(draft.title);

  const save = async () => {
    setEditing(false);
    if (value.trim() === draft.title) return;
    await apiFetch(`/publishing/drafts/${draft.id}`, {
      method: 'PUT',
      body: JSON.stringify({ title: value.trim() }),
    });
    if (onUpdate) onUpdate();
  };

  if (editing) {
    return (
      <input
        autoFocus
        className="text-sm font-medium text-gray-800 bg-white border border-brand-300 rounded px-1.5 py-0.5 w-full outline-none focus:ring-1 focus:ring-brand-400"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setValue(draft.title); setEditing(false); } }}
      />
    );
  }

  return (
    <span
      className="cursor-text hover:bg-gray-100 rounded px-1 -mx-1 transition-colors"
      onDoubleClick={() => setEditing(true)}
      title="Double-click to edit"
    >
      {draft.title}
    </span>
  );
}

function SortableHeader({ label, field, sortField, sortDir, onSort }) {
  const active = sortField === field;
  return (
    <th
      className="pb-2 font-medium pr-4 cursor-pointer select-none hover:text-gray-600 transition-colors"
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <span className={`text-[10px] ${active ? 'text-brand-600' : 'text-gray-300'}`}>
          {active ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
        </span>
      </span>
    </th>
  );
}

function ListView({ drafts, onStatusChange, onDelete, apiFetch, onUpdate }) {
  const [confirmId, setConfirmId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [sortField, setSortField] = useState('');
  const [sortDir, setSortDir] = useState('asc');

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortedDrafts = [...drafts].sort((a, b) => {
    if (!sortField) return 0;
    let aVal = a[sortField] || '';
    let bVal = b[sortField] || '';
    if (sortField === 'planned_date') {
      aVal = aVal || '9999-99-99';
      bVal = bVal || '9999-99-99';
    }
    const cmp = String(aVal).localeCompare(String(bVal));
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const handleCopy = (d) => {
    if (copyDraftToClipboard(d)) {
      setCopiedId(d.id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
            <SortableHeader label="Title" field="title" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
            <SortableHeader label="Platform" field="platform" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
            <SortableHeader label="Status" field="status" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
            <SortableHeader label="Planned Date" field="planned_date" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
            <th className="pb-2 font-medium pr-4">Campaign</th>
            <th className="pb-2 font-medium pr-4">Actions</th>
            <th className="pb-2 font-medium pr-4"></th>
            <th className="pb-2 font-medium pr-4"></th>
          </tr>
        </thead>
        <tbody>
          {sortedDrafts.map((d) => (
            <tr key={d.id} className="border-b border-gray-50 hover:bg-gray-50/50">
              <td className="py-2.5 pr-4 font-medium text-gray-800 max-w-xs">
                <InlineEditableTitle draft={d} apiFetch={apiFetch} onUpdate={onUpdate} />
              </td>
              <td className="py-2.5 pr-4"><span className="badge bg-gray-100 text-gray-600">{d.platform}</span></td>
              <td className="py-2.5 pr-4"><StatusBadge status={d.status} /></td>
              <td className="py-2.5 pr-4 text-gray-500">
                {d.planned_date || '—'}
                {d.planned_time && <span className="text-gray-400 ml-1">{d.planned_time}</span>}
              </td>
              <td className="py-2.5 pr-4 text-gray-400">
                <span className="flex items-center gap-1.5">
                  {d.campaign_id ? `#${d.campaign_id}` : '—'}
                  {d.image_ids && <span className="inline-flex items-center text-[10px] text-brand-500 bg-brand-50 rounded px-1">IMG {d.image_ids.split(',').filter(Boolean).length}</span>}
                </span>
              </td>
              <td className="py-2.5 pr-4">
                <select
                  className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                  value={d.status}
                  onChange={(e) => onStatusChange(d.id, e.target.value)}
                >
                  {DRAFT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
              </td>
              <td className="py-2.5 pr-2">
                <button
                  className="text-xs text-gray-400 hover:text-brand-600 transition-colors"
                  onClick={() => handleCopy(d)}
                  title="Copy post to clipboard"
                >
                  {copiedId === d.id ? 'Copied!' : 'Copy'}
                </button>
              </td>
              <td className="py-2.5">
                {confirmId === d.id ? (
                  <div className="flex items-center gap-1">
                    <button className="text-xs text-red-600 font-medium hover:text-red-800" onClick={() => { onDelete(d.id); setConfirmId(null); }}>Confirm</button>
                    <button className="text-xs text-gray-400 hover:text-gray-600" onClick={() => setConfirmId(null)}>Cancel</button>
                  </div>
                ) : (
                  <button className="text-xs text-red-400 hover:text-red-600 transition-colors" onClick={() => setConfirmId(d.id)} title="Delete draft">
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {drafts.length === 0 && (
        <p className="text-sm text-gray-400 py-8 text-center">No drafts yet. Generate content in the Post Generation tab.</p>
      )}
    </div>
  );
}

const LIBRARY_STATUSES = [
  { key: 'reuse_later',    label: 'Reuse Later',    color: 'text-indigo-600 bg-indigo-50 border-indigo-200' },
  { key: 'turn_into_ad',   label: 'Turn Into Ad',   color: 'text-amber-700 bg-amber-50 border-amber-200' },
  { key: 'turn_into_page', label: 'Turn Into Page', color: 'text-teal-700 bg-teal-50 border-teal-200' },
];

function ContentLibrary({ drafts, onStatusChange, onDelete }) {
  const [expanded, setExpanded] = useState({});
  const libraryDrafts = drafts.filter((d) => ['reuse_later', 'turn_into_ad', 'turn_into_page'].includes(d.status));

  const toggle = (key) => setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));

  if (libraryDrafts.length === 0) return null;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="font-semibold text-gray-800 text-sm">Content Library</h4>
          <p className="text-xs text-gray-400 mt-0.5">Saved content for reuse, ads, or landing pages.</p>
        </div>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{libraryDrafts.length} item{libraryDrafts.length !== 1 ? 's' : ''}</span>
      </div>
      {LIBRARY_STATUSES.map(({ key, label, color }) => {
        const items = libraryDrafts.filter((d) => d.status === key);
        if (items.length === 0) return null;
        const isExpanded = expanded[key] !== false;
        return (
          <div key={key} className="mb-3">
            <button
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border text-sm font-medium ${color} transition-colors hover:opacity-80`}
              onClick={() => toggle(key)}
            >
              <span>{label} ({items.length})</span>
              <span className="text-xs">{isExpanded ? '▾' : '▸'}</span>
            </button>
            {isExpanded && (
              <div className="mt-2 space-y-1.5 pl-2">
                {items.map((d) => (
                  <div key={d.id} className="flex items-center justify-between p-2 rounded-lg bg-gray-50 border border-gray-100">
                    <div className="flex-1 min-w-0 mr-3">
                      <p className="text-sm font-medium text-gray-800 truncate">{d.title}</p>
                      <p className="text-xs text-gray-400">{d.platform}{d.planned_date ? ` · ${d.planned_date}` : ''}</p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <select
                        className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                        value={d.status}
                        onChange={(e) => onStatusChange(d.id, e.target.value)}
                      >
                        {DRAFT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                      </select>
                      {onDelete && (
                        <button
                          className="text-xs text-red-400 hover:text-red-600"
                          onClick={() => onDelete(d.id)}
                          title="Delete"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PublishingQueueTab({ apiFetch }) {
  const [view, setView] = useState('kanban');
  const [drafts, setDrafts] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  const loadDrafts = useCallback(async () => {
    const params = new URLSearchParams();
    if (filterPlatform) params.set('platform', filterPlatform);
    if (filterStatus) params.set('status', filterStatus);
    const r = await apiFetch(`/publishing/drafts?${params}`);
    if (r.ok) setDrafts(await r.json());
  }, [apiFetch, filterPlatform, filterStatus]);

  const loadCalendar = useCallback(async () => {
    const r = await apiFetch('/publishing/calendar');
    if (r.ok) setCalendar(await r.json());
  }, [apiFetch]);

  useEffect(() => { loadDrafts(); loadCalendar(); }, [filterPlatform, filterStatus]); // eslint-disable-line

  const updateStatus = async (id, status) => {
    await apiFetch(`/publishing/drafts/${id}/status?status=${status}`, { method: 'PUT' });
    await loadDrafts();
    await loadCalendar();
  };

  const deleteDraft = async (id) => {
    await apiFetch(`/publishing/drafts/${id}`, { method: 'DELETE' });
    await loadDrafts();
    await loadCalendar();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-800">Publishing Queue</h3>
          <p className="text-sm text-gray-500 mt-0.5">Manage, schedule, and track your content across platforms.</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden">
          {[
            { key: 'kanban',   label: 'Kanban',   icon: '⬛' },
            { key: 'calendar', label: 'Calendar', icon: '📅' },
            { key: 'list',     label: 'List',     icon: '☰' },
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              onClick={() => setView(key)}
              className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-1.5 ${
                view === key ? 'bg-brand-600 text-white' : 'bg-white text-brand-600 hover:bg-brand-50'
              }`}
            >
              {icon} {label}
            </button>
          ))}
        </div>
        <select className="select w-36" value={filterPlatform} onChange={(e) => setFilterPlatform(e.target.value)}>
          <option value="">All platforms</option>
          {PUB_PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="select w-40" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">All statuses</option>
          {DRAFT_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
        <button className="btn-secondary text-xs py-1.5 px-3" onClick={loadDrafts}>Reload</button>
        <span className="ml-auto text-sm text-gray-400">{drafts.length} draft{drafts.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="card">
        {view === 'kanban'   && <KanbanBoard drafts={drafts} onStatusChange={updateStatus} onDelete={deleteDraft} onUpdate={() => { loadDrafts(); loadCalendar(); }} apiFetch={apiFetch} />}
        {view === 'calendar' && <CalendarView drafts={calendar} />}
        {view === 'list'     && <ListView drafts={drafts} onStatusChange={updateStatus} onDelete={deleteDraft} apiFetch={apiFetch} onUpdate={() => { loadDrafts(); loadCalendar(); }} />}
      </div>

      <ContentLibrary drafts={drafts} onStatusChange={updateStatus} onDelete={deleteDraft} />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SocialStudioPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [activeTab, setActiveTab] = useState('post');
  const [form, setForm] = useState(DEFAULT_FORM);
  const [settings, setSettings] = useState({});
  const [albums, setAlbums] = useState([]);
  const [assets, setAssets] = useState([]);
  const [selectedAssets, setSelectedAssets] = useState([]);
  const [result, setResult] = useState(null);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

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

  useEffect(() => {
    if (!isLoggedIn) return;
    loadSettings();
    loadAlbums();
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

  const generate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    setError('');
    setResult(null);
    const selected = assets.filter((asset) => selectedAssets.includes(asset.id));
    const imageContext = selected.map((asset) => `${asset.filename || asset.title} (ID: ${asset.id})`).join(', ');
    const jobDesc = form.job_description
      ? `${form.job_description}\n\nSelected project photos for visual reference: ${imageContext}`
      : `Selected project photos for visual reference: ${imageContext}`;
    const r = await apiFetch('/social/generate-pack', {
      method: 'POST',
      body: JSON.stringify({
        album_id: form.album_id,
        asset_ids: selected.map((asset) => asset.id),
        asset_filenames: selected.map((asset) => asset.filename || asset.title),
        platforms: form.platforms,
        service_category: form.service_category,
        language: form.language,
        tone: form.tone,
        city: form.city,
        cta: form.cta,
        job_description: jobDesc,
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
    const imgIds = selectedAssets.join(',');
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
          image_ids: imgIds,
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
    if (savedAll) {
      setResult(null);
      setError('All drafts saved to the publishing queue for review.');
    }
  };

  const saveSingleDraft = async (draft, status) => {
    setSaving(true);
    setError('');
    const imgIds = selectedAssets.join(',');
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
        image_ids: imgIds,
        status: status,
      }),
    });
    setSaving(false);
    if (r.ok) {
      setError(`Draft saved as "${status.replace(/_/g, ' ')}".`);
      return true;
    }
    setError('Saving draft failed.');
    return false;
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6 max-w-7xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-1">Social Studio</h2>
          <p className="text-gray-500 text-sm">
            Create social content, generate images, manage campaigns, and schedule publishing.
          </p>
        </div>
        <Link href="/settings" className="btn-secondary text-sm" onClick={() => {}}>Settings</Link>
      </div>

      <div className="flex flex-wrap gap-1 mb-6 border-b border-gray-200">
        {SS_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
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

      {activeTab === 'post' && (
        <PostGenerationTab
          form={form}
          setForm={setForm}
          settings={settings}
          albums={albums}
          assets={assets}
          selectedAssets={selectedAssets}
          setSelectedAssets={setSelectedAssets}
          loadAlbumAssets={loadAlbumAssets}
          loadingAssets={loadingAssets}
          generate={generate}
          generating={generating}
          result={result}
          saveDraft={saveDraft}
          saveSingleDraft={saveSingleDraft}
          saving={saving}
          error={error}
          setError={setError}
        />
      )}

      {activeTab === 'image' && (
        <ImageGenerationTab
          albums={albums}
          settings={settings}
          apiFetch={apiFetch}
        />
      )}

      {activeTab === 'campaigns' && (
        <CampaignsTab apiFetch={apiFetch} />
      )}

      {activeTab === 'publishing' && (
        <PublishingQueueTab apiFetch={apiFetch} />
      )}
    </div>
  );
}
