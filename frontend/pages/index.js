import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

const SOURCES = ['google_calendar', 'jobber', 'immich', 'immich-gpt', 'paperless'];

const SOURCE_META = {
  google_calendar: { label: 'Google Calendar', icon: '📅', color: 'brand' },
  jobber:          { label: 'Jobber',          icon: '🔧', color: 'brand' },
  immich:          { label: 'Immich / Photos', icon: '🖼️', color: 'brand' },
  'immich-gpt':    { label: 'Immich-GPT',      icon: '🧠', color: 'brand' },
  paperless:       { label: 'Paperless',       icon: '📄', color: 'brand' },
};

const DEFAULT_QUICK_LINKS = [
  { title: 'Jobber',               icon: '🔧', url: 'https://app.jobber.com',              category: 'Operations' },
  { title: 'Google Calendar',      icon: '📅', url: 'https://calendar.google.com',          category: 'Operations' },
  { title: 'Gmail',                icon: '✉️', url: 'https://mail.google.com',              category: 'Operations' },
  { title: 'Paperless-ngx',        icon: '📄', url: 'http://paperless.local',               category: 'Documents'  },
  { title: 'Immich',               icon: '🖼️', url: 'http://immich.local',                  category: 'Photos'     },
  { title: 'WordPress Admin',      icon: '🌐', url: 'https://bricopro.ca/wp-admin',         category: 'Marketing'  },
  { title: 'Meta Business Suite',  icon: '📣', url: 'https://business.facebook.com',        category: 'Marketing'  },
  { title: 'Google Business',      icon: '⭐', url: 'https://business.google.com',           category: 'Marketing'  },
  { title: 'Canva',                icon: '🎨', url: 'https://canva.com',                    category: 'Marketing'  },
  { title: 'Actual Budget',        icon: '💸', url: 'http://actual.local',                  category: 'Finance'    },
];

const QUICK_LINK_LOGO_DOMAINS = {
  jobber: 'jobber.com',
  'google calendar': 'calendar.google.com',
  gmail: 'mail.google.com',
  'paperless-ngx': 'docs.paperless-ngx.com',
  paperless: 'docs.paperless-ngx.com',
  immich: 'immich.app',
  'wordpress admin': 'wordpress.org',
  'meta business suite': 'facebook.com',
  'google business': 'business.google.com',
  canva: 'canva.com',
  'actual budget': 'actualbudget.org',
};

function logoDomainFor(link) {
  const knownDomain = QUICK_LINK_LOGO_DOMAINS[link.title.toLowerCase()];
  if (knownDomain) return knownDomain;
  try {
    return new URL(link.url).hostname;
  } catch {
    return 'example.com';
  }
}

function logoUrlFor(link) {
  return `https://www.google.com/s2/favicons?domain=${logoDomainFor(link)}&sz=64`;
}

function WidgetCard({ title, icon, status, stale, data, onRefresh, loading }) {
  const statusColor =
    status === 'ok' ? 'text-green-600' :
    status === 'not_connected' ? 'text-red-500' :
    'text-orange-500';

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <h3 className="font-semibold text-gray-800">{title}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${statusColor}`}>
            {status === 'ok' ? (stale ? '⚠ stale' : '● live') : status}
          </span>
          <button
            className="btn-secondary text-xs py-1 px-2"
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? '…' : 'Refresh'}
          </button>
        </div>
      </div>
      {status === 'not_connected' ? (
        <p className="text-sm text-red-500">Integration not connected. Configure in Settings.</p>
      ) : (
        <pre className="text-xs bg-gray-50 rounded-lg p-3 overflow-auto max-h-40 text-gray-600">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function QuickLinksWidget({ links, onAdd, onDelete }) {
  const [form, setForm] = useState({ title: '', url: '', category: 'Operations' });
  const [adding, setAdding] = useState(false);

  return (
    <div className="card col-span-full py-3 mb-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="font-semibold text-gray-800 text-sm">Quick Links</h3>
        <button className="btn-secondary text-xs py-1 px-3" onClick={() => setAdding((v) => !v)}>
          {adding ? 'Cancel' : '+ Add Link'}
        </button>
      </div>
      {adding && (
        <form
          className="flex flex-wrap gap-2 mb-4 p-3 bg-gray-50 rounded-lg"
          onSubmit={(e) => { e.preventDefault(); onAdd(form); setAdding(false); setForm({ title: '', url: '', category: 'Operations' }); }}
        >
          <input className="input flex-1 min-w-32" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <input className="input flex-1 min-w-48" placeholder="https://..." value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required />
          <input className="input w-36" placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          <button type="submit" className="btn-primary text-sm">Save</button>
        </form>
      )}
      {links.length > 0 ? (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {links.map((link) => (
            <div key={link.id} className="relative group flex-shrink-0">
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                title={link.title}
                aria-label={link.title}
                className="w-11 h-11 rounded-xl border border-gray-100 bg-white hover:bg-brand-50 hover:border-brand-200 shadow-sm flex items-center justify-center transition-colors"
              >
                <img
                  src={logoUrlFor(link)}
                  alt=""
                  className="w-6 h-6 object-contain"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              </a>
              <button
                className="absolute -right-1 -top-1 w-4 h-4 rounded-full bg-white border border-gray-200 text-gray-300 hover:text-red-400 text-xs leading-none opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={() => onDelete(link.id)}
                title={`Remove ${link.title}`}
                aria-label={`Remove ${link.title}`}
              >
                ×
              </button>
          </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-400">No quick links yet. Add some above.</p>
      )}
    </div>
  );
}

function ProcessingSummary({ summary }) {
  const cards = [
    {
      label: 'Images',
      value: summary?.images_pending ?? 0,
      detail: 'pending in Immich-GPT',
      icon: '🧠',
      color: 'from-brand-600 to-brand-700',
    },
    {
      label: 'Documents',
      value: summary?.documents_pending ?? 0,
      detail: 'pending in Paperless-GPT',
      icon: '📄',
      color: 'from-accent-500 to-accent-600',
    },
    {
      label: 'Review',
      value: summary?.needs_review ?? 0,
      detail: 'items need attention',
      icon: '👀',
      color: 'from-gray-700 to-gray-900',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {cards.map((card) => (
        <div key={card.label} className={`rounded-2xl bg-gradient-to-br ${card.color} p-5 text-white shadow-sm`}>
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-white/75">{card.label} to process</p>
              <p className="text-4xl font-black mt-2">{card.value}</p>
            </div>
            <span className="w-12 h-12 rounded-2xl bg-white/15 flex items-center justify-center text-xl">
              {card.icon}
            </span>
          </div>
          <p className="text-xs text-white/70 mt-4">{card.detail}</p>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [dashboard, setDashboard] = useState({});
  const [integrations, setIntegrations] = useState([]);
  const [quickLinks, setQuickLinks] = useState([]);
  const [processingSummary, setProcessingSummary] = useState(null);
  const [refreshing, setRefreshing] = useState({});

  const loadDashboard = useCallback(async () => {
    const r = await apiFetch('/dashboard');
    if (r.ok) setDashboard(await r.json());
  }, [apiFetch]);

  const loadIntegrations = useCallback(async () => {
    const r = await apiFetch('/integrations');
    if (r.ok) setIntegrations(await r.json());
  }, [apiFetch]);

  const loadQuickLinks = useCallback(async () => {
    const r = await apiFetch('/quick-links');
    if (r.ok) setQuickLinks(await r.json());
  }, [apiFetch]);

  const loadProcessingSummary = useCallback(async () => {
    const r = await apiFetch('/processing/summary');
    if (r.ok) setProcessingSummary(await r.json());
  }, [apiFetch]);

  const seedLinks = useCallback(async () => {
    for (const link of DEFAULT_QUICK_LINKS) {
      await apiFetch('/quick-links', {
        method: 'POST',
        body: JSON.stringify({ ...link, sort_order: 0, is_active: true }),
      });
    }
    await loadQuickLinks();
  }, [apiFetch, loadQuickLinks]);

  useEffect(() => {
    if (!isLoggedIn) return;
    loadDashboard();
    loadIntegrations();
    loadProcessingSummary();
    loadQuickLinks().then(async () => {
      const r = await apiFetch('/quick-links');
      if (r.ok) {
        const links = await r.json();
        if (links.length === 0) await seedLinks();
      }
    });
  }, [isLoggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshSource = async (source) => {
    setRefreshing((p) => ({ ...p, [source]: true }));
    await apiFetch(`/dashboard/refresh/${source}`, { method: 'POST' });
    await loadDashboard();
    await loadIntegrations();
    await loadProcessingSummary();
    setRefreshing((p) => ({ ...p, [source]: false }));
  };

  const addQuickLink = async (form) => {
    await apiFetch('/quick-links', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        icon: 'link',
        sort_order: 0,
        is_active: true,
      }),
    });
    await loadQuickLinks();
  };

  const deleteQuickLink = async (id) => {
    await apiFetch(`/quick-links/${id}`, { method: 'DELETE' });
    await loadQuickLinks();
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6">
      <QuickLinksWidget
        links={quickLinks.filter((l) => l.is_active)}
        onAdd={addQuickLink}
        onDelete={deleteQuickLink}
      />

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Dashboard</h2>
          <p className="text-gray-500 text-sm mt-0.5">Business overview — today at a glance</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => { SOURCES.forEach((s) => refreshSource(s)); }}
        >
          Refresh All
        </button>
      </div>

      <ProcessingSummary summary={processingSummary} />

      {/* Integration status bar */}
      <div className="flex gap-3 flex-wrap mb-6">
        {integrations.map((i) => (
          <div key={i.provider} className="flex items-center gap-1.5 bg-white border border-gray-100 rounded-full px-3 py-1 shadow-sm">
            <span className={`w-2 h-2 rounded-full ${i.status === 'ok' ? 'bg-green-400' : i.status === 'not_connected' ? 'bg-red-400' : 'bg-yellow-400'}`} />
            <span className="text-xs text-gray-600">{i.provider.replace('_', ' ')}</span>
          </div>
        ))}
      </div>

      {/* Integration widgets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {SOURCES.map((src) => {
          const meta = SOURCE_META[src];
          const w = dashboard[src] || {};
          return (
            <WidgetCard
              key={src}
              title={meta.label}
              icon={meta.icon}
              status={w.status || 'unknown'}
              stale={w.stale}
              data={w.data || {}}
              onRefresh={() => refreshSource(src)}
              loading={refreshing[src]}
            />
          );
        })}
      </div>

    </div>
  );
}
