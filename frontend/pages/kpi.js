import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

const EMPTY = {
  title: '',
  platform: 'facebook',
  post_url: '',
  campaign_name: '',
  spend: 0,
  impressions: 0,
  reach: 0,
  clicks: 0,
  leads: 0,
  messages: 0,
  calls: 0,
  engagements: 0,
  engagement_rate: 0,
  notes: '',
};

function formatCurrency(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function formatNum(v) {
  const n = Number(v || 0);
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

const PLATFORM_COLORS = {
  facebook: 'bg-blue-100 text-blue-700',
  instagram: 'bg-pink-100 text-pink-700',
  gbp: 'bg-green-100 text-green-700',
  linkedin: 'bg-blue-100 text-blue-800',
  google_ads: 'bg-yellow-100 text-yellow-700',
};

function PlatformBadge({ platform }) {
  const cls = PLATFORM_COLORS[platform] || 'bg-gray-100 text-gray-600';
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{platform}</span>;
}

function MetricCard({ label, value, sub }) {
  return (
    <div className="card">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-3xl font-black text-brand-600 mt-2">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-2">{sub}</p>}
    </div>
  );
}

// ── Sparkline (SVG micro-chart) ───────────────────────────────────────────────

function Sparkline({ data, color = '#6366f1' }) {
  if (!data || data.length < 2) return <span className="text-xs text-gray-300">—</span>;
  const vals = data.map((d) => d.impressions || 0);
  const max = Math.max(...vals, 1);
  const w = 80, h = 28;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * w},${h - (v / max) * h}`).join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={pts} />
    </svg>
  );
}

// ── Per-Post Tab ──────────────────────────────────────────────────────────────

function PostRow({ item, apiFetch, onSync }) {
  const { draft, metric } = item;
  const [syncing, setSyncing] = useState(false);
  const [snapshots, setSnapshots] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const sync = async (e) => {
    e.stopPropagation();
    setSyncing(true);
    await apiFetch(`/kpi/sync-post/${draft.id}`, { method: 'POST' });
    setSyncing(false);
    if (onSync) onSync();
  };

  const loadSnapshots = async () => {
    if (snapshots) return;
    const r = await apiFetch(`/kpi/posts/${draft.id}/snapshots`);
    if (r.ok) setSnapshots(await r.json());
  };

  const toggle = () => {
    setExpanded((v) => !v);
    if (!expanded) loadSnapshots();
  };

  const platformLink = () => {
    if (!draft.platform_post_id) return null;
    if (draft.platform === 'facebook') return `https://www.facebook.com/${draft.platform_post_id}`;
    if (draft.platform === 'instagram') return `https://www.instagram.com/p/${draft.platform_post_id}/`;
    return null;
  };

  const link = platformLink();

  return (
    <>
      <tr
        className={`border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors ${expanded ? 'bg-gray-50' : ''}`}
        onClick={toggle}
      >
        <td className="py-3 pr-3">
          <div className="flex items-center gap-2">
            {draft.platform_post_id
              ? <span className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" title="Live" />
              : draft.status === 'failed'
              ? <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" title="Failed" />
              : <span className="w-2 h-2 rounded-full bg-gray-300 flex-shrink-0" title="Scheduled" />
            }
            <span className="text-sm font-medium text-gray-800 truncate max-w-[180px]">{draft.title || '(untitled)'}</span>
          </div>
        </td>
        <td className="py-3 pr-3"><PlatformBadge platform={draft.platform} /></td>
        <td className="py-3 pr-3 text-xs text-gray-500">
          {draft.published_at ? new Date(draft.published_at).toLocaleDateString() : draft.planned_date || '—'}
        </td>
        <td className="py-3 pr-3 text-sm text-gray-700">{metric ? formatNum(metric.impressions) : '—'}</td>
        <td className="py-3 pr-3 text-sm text-gray-700">{metric ? formatNum(metric.reach) : '—'}</td>
        <td className="py-3 pr-3 text-sm text-gray-700">{metric ? formatNum(metric.clicks) : '—'}</td>
        <td className="py-3 pr-3 text-sm text-gray-700">{metric ? formatNum(metric.engagements) : '—'}</td>
        <td className="py-3 pr-3">
          <div className="flex items-center gap-2">
            {snapshots && <Sparkline data={snapshots} />}
            {draft.platform_post_id && (
              <button
                className="text-xs px-2 py-1 rounded border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors whitespace-nowrap"
                onClick={sync}
                disabled={syncing}
              >
                {syncing ? '…' : 'Sync'}
              </button>
            )}
            {link && (
              <a
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-gray-400 hover:text-gray-600"
                onClick={(e) => e.stopPropagation()}
              >
                ↗
              </a>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50 border-b border-gray-100">
          <td colSpan={8} className="px-4 py-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Post ID</p>
                <p className="font-mono text-xs text-gray-600 truncate">{draft.platform_post_id || '—'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Account</p>
                <p className="text-xs text-gray-600 truncate">{draft.platform_account_id || '—'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Spend</p>
                <p className="text-xs text-gray-700">{metric ? formatCurrency(metric.spend) : '—'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Engagement rate</p>
                <p className="text-xs text-gray-700">{metric ? `${metric.engagement_rate}%` : '—'}</p>
              </div>
              {metric?.notes && (
                <div className="col-span-2">
                  <p className="text-xs text-gray-400 mb-0.5">Notes</p>
                  <p className="text-xs text-gray-600">{metric.notes}</p>
                </div>
              )}
              {draft.publish_error && (
                <div className="col-span-4">
                  <p className="text-xs text-red-500">Error: {draft.publish_error}</p>
                </div>
              )}
              {snapshots && snapshots.length > 0 && (
                <div className="col-span-4">
                  <p className="text-xs text-gray-400 mb-1">Impressions over time ({snapshots.length} syncs)</p>
                  <div className="flex items-end gap-1 h-10">
                    {snapshots.map((s, i) => {
                      const max = Math.max(...snapshots.map((x) => x.impressions), 1);
                      const pct = Math.round((s.impressions / max) * 100);
                      return (
                        <div key={i} className="flex-1 bg-brand-200 rounded-sm" style={{ height: `${Math.max(pct, 4)}%` }} title={`${s.impressions} impressions · ${new Date(s.captured_at).toLocaleDateString()}`} />
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function PerPostTab({ apiFetch }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await apiFetch('/kpi/posts');
    if (r.ok) setPosts(await r.json());
    setLoading(false);
  }, [apiFetch]);

  useEffect(() => { load(); }, []); // eslint-disable-line

  const syncAll = async () => {
    setSyncingAll(true);
    setSyncResult(null);
    const r = await apiFetch('/kpi/sync-all', { method: 'POST' });
    if (r.ok) {
      const data = await r.json();
      setSyncResult(data);
      await load();
    }
    setSyncingAll(false);
  };

  const published = posts.filter((p) => p.draft.platform_post_id);
  const scheduled = posts.filter((p) => !p.draft.platform_post_id && p.draft.status === 'scheduled');

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-sm text-gray-500">{published.length} live post{published.length !== 1 ? 's' : ''} · {scheduled.length} scheduled</p>
        </div>
        <button
          className="btn-primary text-sm py-1.5 px-4"
          onClick={syncAll}
          disabled={syncingAll || published.length === 0}
        >
          {syncingAll ? 'Syncing…' : 'Sync All'}
        </button>
      </div>

      {syncResult && (
        <div className="mb-4 rounded-lg bg-green-50 border border-green-100 px-4 py-2 text-sm text-green-700">
          Synced {syncResult.synced} post{syncResult.synced !== 1 ? 's' : ''}.
          {syncResult.failed?.length > 0 && ` ${syncResult.failed.length} failed.`}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-gray-400 text-center py-8">Loading posts…</p>
      ) : posts.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-500 font-medium">No published or scheduled posts yet.</p>
          <p className="text-sm text-gray-400 mt-1">Publish a draft from the Social Studio to see it here.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                {['Post', 'Platform', 'Date', 'Impressions', 'Reach', 'Clicks', 'Engagements', ''].map((h) => (
                  <th key={h} className="pb-2 pr-3 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {posts.map((item) => (
                <PostRow key={item.draft.id} item={item} apiFetch={apiFetch} onSync={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Manual Entry Tab ──────────────────────────────────────────────────────────

function ManualEntryTab({ apiFetch }) {
  const [records, setRecords] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch('/kpi/records');
      if (r.ok) { setRecords(await r.json()); setLoadError(null); }
      else setLoadError('Failed to load KPI records.');
    } catch { setLoadError('Failed to load KPI records.'); }
  }, [apiFetch]);

  useEffect(() => { load(); }, []); // eslint-disable-line

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    const r = await apiFetch('/kpi/records', { method: 'POST', body: JSON.stringify(form) });
    if (r.ok) setForm(EMPTY);
    setSaving(false);
    await load();
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
      <div className="card xl:col-span-1">
        <h3 className="font-semibold text-gray-800 mb-4">Add performance result</h3>
        <form onSubmit={save} className="space-y-3">
          <div>
            <label className="label">Title</label>
            <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Platform</label>
              <select className="select" value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
                {['facebook', 'instagram', 'google_ads', 'gbp', 'linkedin', 'website'].map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Campaign</label>
              <input className="input" value={form.campaign_name} onChange={(e) => setForm({ ...form, campaign_name: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="label">Post / ad URL</label>
            <input className="input" value={form.post_url} onChange={(e) => setForm({ ...form, post_url: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {['spend', 'impressions', 'reach', 'clicks', 'leads', 'messages', 'calls', 'engagements', 'engagement_rate'].map((key) => (
              <div key={key}>
                <label className="label capitalize">{key.replace('_', ' ')}</label>
                <input
                  className="input"
                  type="number"
                  step={key === 'engagement_rate' ? '0.01' : '1'}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
                />
              </div>
            ))}
          </div>
          <div>
            <label className="label">Notes</label>
            <textarea className="input h-20 resize-y" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={saving}>{saving ? 'Saving…' : 'Save KPI Record'}</button>
        </form>
      </div>

      <div className="card xl:col-span-2">
        <h3 className="font-semibold text-gray-800 mb-4">Recent performance</h3>
        {loadError && (
          <div className="mb-3 rounded-lg bg-red-50 border border-red-100 px-4 py-2 text-sm text-red-700 flex items-center justify-between">
            <span>{loadError}</span>
            <button className="text-xs opacity-70 hover:opacity-100 ml-3" onClick={load}>Retry</button>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                {['Title', 'Platform', 'Campaign', 'Spend', 'Leads', 'Clicks', 'CPL'].map((h) => (
                  <th key={h} className="pb-2 pr-4 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-50">
                  <td className="py-3 pr-4 font-medium text-gray-800">{r.post_url ? <a className="hover:text-brand-600" href={r.post_url} target="_blank" rel="noopener noreferrer">{r.title}</a> : r.title}</td>
                  <td className="py-3 pr-4"><PlatformBadge platform={r.platform} /></td>
                  <td className="py-3 pr-4 text-gray-500">{r.campaign_name || '—'}</td>
                  <td className="py-3 pr-4">{formatCurrency(r.spend)}</td>
                  <td className="py-3 pr-4">{r.leads}</td>
                  <td className="py-3 pr-4">{r.clicks}</td>
                  <td className="py-3 pr-4">{formatCurrency(r.cost_per_lead)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {records.length === 0 && <p className="text-sm text-gray-400 text-center py-8">No KPI records yet.</p>}
        </div>
      </div>
    </div>
  );
}

// ── Summary Tab ───────────────────────────────────────────────────────────────

function SummaryTab({ apiFetch }) {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    apiFetch('/kpi/summary').then(async (r) => { if (r.ok) setSummary(await r.json()); });
  }, []); // eslint-disable-line

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          ['Total Spend', formatCurrency(summary?.total_spend ?? summary?.spend), 'All tracked ad budget'],
          ['Total Leads', formatNum(summary?.total_leads ?? summary?.leads ?? 0), 'Tracked conversions'],
          ['Total Clicks', formatNum(summary?.total_clicks ?? summary?.clicks ?? 0), 'Traffic actions'],
          ['Cost / Lead', formatCurrency(summary?.cost_per_lead), 'Efficiency across all posts'],
        ].map(([label, value, sub]) => (
          <MetricCard key={label} label={label} value={value} sub={sub} />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[
          ['Total Impressions', formatNum(summary?.total_impressions ?? summary?.impressions ?? 0), 'Across all tracked posts'],
          ['Click-through Rate', `${summary?.click_through_rate ?? 0}%`, 'Clicks ÷ Impressions'],
        ].map(([label, value, sub]) => (
          <MetricCard key={label} label={label} value={value} sub={sub} />
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'posts', label: 'Per-Post Performance' },
  { key: 'manual', label: 'Manual Entry' },
  { key: 'summary', label: 'Summary' },
];

export default function KPIPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [activeTab, setActiveTab] = useState('posts');

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">KPI Tracking</h2>
      <p className="text-gray-500 text-sm mb-5">Track post engagement and ad performance across Meta, Google, and other platforms.</p>

      <div className="flex border-b border-gray-200 mb-6 gap-0">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === key
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'posts'   && <PerPostTab   apiFetch={apiFetch} />}
      {activeTab === 'manual'  && <ManualEntryTab apiFetch={apiFetch} />}
      {activeTab === 'summary' && <SummaryTab   apiFetch={apiFetch} />}
    </div>
  );
}
