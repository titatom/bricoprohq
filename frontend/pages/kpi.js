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
  engagement: 0,
  notes: '',
};

function formatCurrency(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

export default function KPIPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const [recordsRes, summaryRes] = await Promise.all([
      apiFetch('/kpi/records'),
      apiFetch('/kpi/summary'),
    ]);
    if (recordsRes.ok) setRecords(await recordsRes.json());
    if (summaryRes.ok) setSummary(await summaryRes.json());
  }, [apiFetch]);

  useEffect(() => { if (isLoggedIn) load(); }, [isLoggedIn]); // eslint-disable-line

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    await apiFetch('/kpi/records', { method: 'POST', body: JSON.stringify(form) });
    setForm(EMPTY);
    setSaving(false);
    await load();
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">KPI Tracking</h2>
      <p className="text-gray-500 text-sm mb-6">Track post and ad engagement after publishing on Meta, Google, and other platforms.</p>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {[
          ['Spend', formatCurrency(summary?.spend), 'Ad budget used'],
          ['Leads', summary?.leads || 0, 'Tracked leads'],
          ['Clicks', summary?.clicks || 0, 'Traffic actions'],
          ['Cost / Lead', formatCurrency(summary?.cost_per_lead), 'Efficiency'],
        ].map(([label, value, detail]) => (
          <div key={label} className="card">
            <p className="text-sm text-gray-500">{label}</p>
            <p className="text-3xl font-black text-brand-600 mt-2">{value}</p>
            <p className="text-xs text-gray-400 mt-2">{detail}</p>
          </div>
        ))}
      </div>

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
              {['spend', 'impressions', 'reach', 'clicks', 'leads', 'messages', 'calls', 'engagement'].map((key) => (
                <div key={key}>
                  <label className="label capitalize">{key}</label>
                  <input
                    className="input"
                    type="number"
                    step={key === 'spend' ? '0.01' : '1'}
                    value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <div>
              <label className="label">Notes</label>
              <textarea className="input h-20 resize-y" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <button type="submit" className="btn-primary w-full" disabled={saving}>{saving ? 'Saving...' : 'Save KPI Record'}</button>
          </form>
        </div>

        <div className="card xl:col-span-2">
          <h3 className="font-semibold text-gray-800 mb-4">Recent performance</h3>
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
                    <td className="py-3 pr-4"><span className="badge bg-gray-100 text-gray-600">{r.platform}</span></td>
                    <td className="py-3 pr-4 text-gray-500">{r.campaign_name || '-'}</td>
                    <td className="py-3 pr-4">{formatCurrency(r.spend)}</td>
                    <td className="py-3 pr-4">{r.leads}</td>
                    <td className="py-3 pr-4">{r.clicks}</td>
                    <td className="py-3 pr-4">{formatCurrency(r.cost_per_lead)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {records.length === 0 && <p className="text-sm text-gray-400 text-center py-8">No KPI records yet. Add your first Meta or Google result.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
