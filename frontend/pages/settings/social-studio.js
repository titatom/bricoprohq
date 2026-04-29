import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '../../context/AuthContext';
import LoginForm from '../../components/LoginForm';

const DEFAULTS = {
  default_album_id: '',
  image_model: 'openai/gpt-4o-mini',
  copy_model: 'openai/gpt-4o-mini',
  default_language: 'fr',
  default_platforms: 'facebook,instagram,gbp',
  brand_voice: 'Friendly, local, practical, trustworthy Bricopro expert.',
  facebook_account: '',
  instagram_account: '',
  google_business_account: '',
  meta_account_id: '',
  google_ads_account_id: '',
  meta_ads_account: '',
  google_ads_account: '',
  before_after_enabled: 'true',
};

export default function SocialStudioSettingsPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [form, setForm] = useState(DEFAULTS);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const r = await apiFetch('/social/settings');
    if (r.ok) setForm({ ...DEFAULTS, ...(await r.json()) });
  }, [apiFetch]);

  useEffect(() => { if (isLoggedIn) load(); }, [isLoggedIn]); // eslint-disable-line

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

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6 max-w-4xl">
      <div className="mb-6">
        <Link href="/settings" className="text-sm text-brand-600 hover:text-brand-800">← Back to Settings</Link>
        <h2 className="text-2xl font-bold text-gray-900 mt-2">Social Studio Settings</h2>
        <p className="text-gray-500 text-sm mt-0.5">
          Configure album analysis, AI model choices, brand voice, and social account references.
        </p>
      </div>

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
          <h3 className="font-semibold text-gray-800 mb-4">Social accounts</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Facebook Page / account</label>
              <input className="input" value={form.facebook_account} onChange={(e) => setForm({ ...form, facebook_account: e.target.value })} placeholder="Facebook page reference" />
            </div>
            <div>
              <label className="label">Instagram account</label>
              <input className="input" value={form.instagram_account} onChange={(e) => setForm({ ...form, instagram_account: e.target.value })} placeholder="@bricopro" />
            </div>
            <div>
              <label className="label">Google Business account</label>
              <input className="input" value={form.google_business_account} onChange={(e) => setForm({ ...form, google_business_account: e.target.value })} placeholder="Business Profile reference" />
            </div>
            <div>
              <label className="label">Meta Ads account ID</label>
              <input className="input" value={form.meta_ads_account || form.meta_account_id} onChange={(e) => setForm({ ...form, meta_ads_account: e.target.value, meta_account_id: e.target.value })} placeholder="Business / ad account reference" />
            </div>
            <div>
              <label className="label">Google Ads account ID</label>
              <input className="input" value={form.google_ads_account || form.google_ads_account_id} onChange={(e) => setForm({ ...form, google_ads_account: e.target.value, google_ads_account_id: e.target.value })} placeholder="Customer ID" />
            </div>
          </div>
        </section>

        <div className="flex gap-2">
          <button className="btn-primary" type="submit" disabled={saving}>
            {saving ? 'Saving...' : saved ? 'Saved' : 'Save Social Studio Settings'}
          </button>
          <Link href="/social-studio" className="btn-secondary">Open Social Studio</Link>
        </div>
      </form>
    </div>
  );
}
