import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

const SOURCES = ['google_calendar', 'jobber', 'immich', 'paperless'];

const SOURCE_META = {
  google_calendar: { label: 'Google Calendar', icon: '📅', color: 'brand' },
  jobber:          { label: 'Jobber',          icon: '🔧', color: 'brand' },
  immich:          { label: 'Immich / Photos', icon: '🖼️', color: 'brand' },
  paperless:       { label: 'Paperless',       icon: '📄', color: 'brand' },
};

const DEFAULT_WIDGET_SETTINGS = {
  paperless: { tag: 'ai-processed', limit: '5' },
  immich: { album_id: '', limit: '6' },
  jobber: { limit: '5', show_client: 'true', show_status: 'true', show_date: 'true' },
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

function QuickLinkIcon({ link }) {
  const icon = (link.icon || '').trim();
  if (icon && icon !== 'link') {
    if (/^https?:\/\//i.test(icon)) {
      return <img src={icon} alt="" className="w-6 h-6 object-contain" loading="lazy" referrerPolicy="no-referrer" />;
    }
    return <span className="text-xl leading-none">{icon}</span>;
  }
  return (
    <img
      src={logoUrlFor(link)}
      alt=""
      className="w-6 h-6 object-contain"
      loading="lazy"
      referrerPolicy="no-referrer"
    />
  );
}

function WidgetHeader({ title, icon, status, stale, onRefresh, loading, onConfigure }) {
  const statusColor =
    status === 'ok' ? 'text-green-600' :
    status === 'not_connected' ? 'text-red-500' :
    'text-orange-500';

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <h3 className="font-semibold text-gray-800">{title}</h3>
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-medium ${statusColor}`}>
          {status === 'ok' ? (stale ? '⚠ stale' : '● live') : status}
        </span>
        {onConfigure && (
          <button
            className="w-7 h-7 rounded-full border border-gray-200 text-gray-400 hover:text-gray-700 hover:bg-gray-50"
            onClick={onConfigure}
            title={`Configure ${title}`}
            aria-label={`Configure ${title}`}
          >
            ⚙
          </button>
        )}
        <button
          className="btn-secondary text-xs py-1 px-2"
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? '…' : 'Refresh'}
        </button>
      </div>
    </div>
  );
}

function WidgetSettingsModal({ source, settings, onClose, onSave }) {
  const [form, setForm] = useState(settings);
  const isPaperless = source === 'paperless';
  const isJobber = source === 'jobber';
  const title = isPaperless ? 'Paperless dashboard settings' : isJobber ? 'Jobber dashboard settings' : 'Immich dashboard settings';

  return (
    <div className="fixed inset-0 z-50 bg-gray-900/30 flex items-center justify-center p-4">
      <form
        className="bg-white rounded-2xl shadow-xl p-5 w-full max-w-md"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(source, form);
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900">
            {title}
          </h3>
          <button type="button" className="text-gray-400 hover:text-gray-700" onClick={onClose}>×</button>
        </div>

        <div className="space-y-3">
          {isPaperless && (
            <div>
              <label className="label">Document tag</label>
              <input
                className="input"
                value={form.tag || ''}
                onChange={(e) => setForm({ ...form, tag: e.target.value })}
                placeholder="ai-processed"
              />
              <p className="text-xs text-gray-400 mt-1">Only latest documents with this tag are shown.</p>
            </div>
          )}
          {!isPaperless && !isJobber && (
            <div>
              <label className="label">Album ID</label>
              <input
                className="input"
                value={form.album_id || ''}
                onChange={(e) => setForm({ ...form, album_id: e.target.value })}
                placeholder="Immich album ID"
              />
              <p className="text-xs text-gray-400 mt-1">Leave blank to show the latest assets.</p>
            </div>
          )}
          {isJobber && (
            <div className="grid grid-cols-1 gap-2 rounded-lg bg-gray-50 p-3">
              {[
                ['show_client', 'Show client'],
                ['show_status', 'Show status'],
                ['show_date', 'Show start date'],
              ].map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={form[key] !== 'false'}
                    onChange={(e) => setForm({ ...form, [key]: e.target.checked ? 'true' : 'false' })}
                  />
                  {label}
                </label>
              ))}
            </div>
          )}
          <div>
            <label className="label">Items to show</label>
            <input
              className="input"
              type="number"
              min="1"
              max="50"
              value={form.limit || ''}
              onChange={(e) => setForm({ ...form, limit: e.target.value })}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button type="button" className="btn-secondary text-sm" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary text-sm">Save settings</button>
        </div>
      </form>
    </div>
  );
}

function PaperlessWidget({ title, icon, status, stale, data, onRefresh, loading, onConfigure }) {
  const docs = data?.recent_documents || [];

  return (
    <div className="card flex flex-col gap-3">
      <WidgetHeader title={title} icon={icon} status={status} stale={stale} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />
      {status === 'not_connected' ? (
        <p className="text-sm text-red-500">Integration not connected. Configure in Settings.</p>
      ) : docs.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-400">
            Latest documents tagged <span className="font-medium text-gray-600">{data?.tag || 'ai-processed'}</span>
          </p>
          {docs.map((doc) => (
            <a
              key={doc.id || doc.title}
              href={doc.document_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="block rounded-lg border border-gray-100 p-3 hover:border-brand-200 hover:bg-brand-50 transition-colors"
            >
              <div className="font-medium text-sm text-gray-800">{doc.title || 'Untitled document'}</div>
              {doc.added && <div className="text-xs text-gray-400 mt-1">{new Date(doc.added).toLocaleString()}</div>}
            </a>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No matching documents found. Use the settings wheel to change the tag.</p>
      )}
    </div>
  );
}

function ImmichThumbnail({ asset }) {
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
    return <img src={src} alt={asset.filename || 'Immich asset'} className="w-full h-full object-cover" loading="lazy" />;
  }

  return (
    <div className="w-full h-full flex items-center justify-center text-xs text-gray-400 text-center p-2">
      {failed ? 'Preview unavailable' : asset.filename || 'Photo'}
    </div>
  );
}

function ImmichWidget({ title, icon, status, stale, data, onRefresh, loading, onConfigure }) {
  const assets = data?.recent_assets || [];

  return (
    <div className="card flex flex-col gap-3">
      <WidgetHeader title={title} icon={icon} status={status} stale={stale} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />
      {status === 'not_connected' ? (
        <p className="text-sm text-red-500">Integration not connected. Configure in Settings.</p>
      ) : assets.length > 0 ? (
        <div className="grid grid-cols-3 gap-2">
          {assets.map((asset) => (
            <a
              key={asset.id || asset.filename}
              href={asset.asset_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              title={asset.filename}
              className="aspect-square rounded-xl bg-gray-100 overflow-hidden border border-gray-100 hover:border-brand-200"
            >
              <ImmichThumbnail asset={asset} />
            </a>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No assets found. Use the settings wheel to choose an album.</p>
      )}
    </div>
  );
}

function JobberWidget({ title, icon, status, stale, data, settings, onRefresh, loading, onConfigure }) {
  const jobs = data?.upcoming_jobs || [];
  const limit = Math.max(1, Math.min(10, Number(settings?.limit || 5)));
  const visibleJobs = jobs.slice(0, limit);
  const showClient = settings?.show_client !== 'false';
  const showStatus = settings?.show_status !== 'false';
  const showStart = settings?.show_start !== 'false';

  return (
    <div className="card flex flex-col gap-3">
      <WidgetHeader title={title} icon={icon} status={status} stale={stale} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />
      {status === 'not_connected' ? (
        <p className="text-sm text-red-500">Integration not connected. Configure in Settings.</p>
      ) : visibleJobs.length > 0 ? (
        <div className="space-y-2">
          {visibleJobs.map((job, idx) => {
            const clientName = job.client?.name || job.clientName || '';
            const start = job.startAt || job.start_at || job.start;
            return (
              <div key={`${job.id || job.title || 'job'}-${idx}`} className="rounded-lg border border-gray-100 p-3 bg-white">
                <div className="font-medium text-sm text-gray-800">{job.title || 'Untitled job'}</div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
                  {showClient && clientName && <span>{clientName}</span>}
                  {showStatus && job.jobStatus && <span>{job.jobStatus}</span>}
                  {showStart && start && <span>{new Date(start).toLocaleString()}</span>}
                </div>
              </div>
            );
          })}
          {data?.count > visibleJobs.length && (
            <p className="text-xs text-gray-400">{data.count - visibleJobs.length} more jobs not shown.</p>
          )}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No upcoming jobs found.</p>
      )}
    </div>
  );
}

function WidgetCard({ source, title, icon, status, stale, data, settings, onRefresh, loading, onConfigure }) {
  if (source === 'jobber') {
    return <JobberWidget title={title} icon={icon} status={status} stale={stale} data={data} settings={settings} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />;
  }
  if (source === 'paperless') {
    return <PaperlessWidget title={title} icon={icon} status={status} stale={stale} data={data} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />;
  }
  if (source === 'immich') {
    return <ImmichWidget title={title} icon={icon} status={status} stale={stale} data={data} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />;
  }

  return (
    <div className="card flex flex-col gap-3">
      <WidgetHeader title={title} icon={icon} status={status} stale={stale} onRefresh={onRefresh} loading={loading} />
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

function QuickLinkForm({ form, setForm, onSubmit, onCancel, submitLabel }) {
  return (
    <form
      className="flex flex-wrap justify-center gap-2 mb-4 p-3 bg-gray-50 rounded-lg"
      onSubmit={onSubmit}
    >
      <input className="input w-20" placeholder="Icon" value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} />
      <input className="input flex-1 min-w-32" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
      <input className="input flex-1 min-w-48" placeholder="https://..." value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required />
      <input className="input w-36" placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
      <button type="submit" className="btn-primary text-sm">{submitLabel}</button>
      <button type="button" className="btn-secondary text-sm" onClick={onCancel}>Cancel</button>
    </form>
  );
}

function QuickLinksWidget({ links, onAdd, onUpdate, onDelete }) {
  const emptyForm = { title: '', url: '', category: 'Operations', icon: '' };
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);

  const resetForm = () => {
    setForm(emptyForm);
    setEditing(null);
    setAdding(false);
  };

  const startAdd = () => {
    setForm(emptyForm);
    setEditing(null);
    setAdding((v) => !v);
  };

  const startEdit = (link) => {
    setForm({
      title: link.title || '',
      url: link.url || '',
      category: link.category || 'Operations',
      icon: link.icon === 'link' ? '' : (link.icon || ''),
    });
    setEditing(link);
    setAdding(false);
  };

  const submitAdd = async (e) => {
    e.preventDefault();
    await onAdd(form);
    resetForm();
  };

  const submitEdit = async (e) => {
    e.preventDefault();
    await onUpdate(editing, form);
    resetForm();
  };

  return (
    <div className="card col-span-full py-3 mb-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="font-semibold text-gray-800 text-sm">Quick Links</h3>
        <button className="btn-secondary text-xs py-1 px-3" onClick={startAdd}>
          {adding ? 'Cancel' : '+ Add Link'}
        </button>
      </div>
      {adding && (
        <QuickLinkForm form={form} setForm={setForm} onSubmit={submitAdd} onCancel={resetForm} submitLabel="Add" />
      )}
      {editing && (
        <QuickLinkForm form={form} setForm={setForm} onSubmit={submitEdit} onCancel={resetForm} submitLabel="Save" />
      )}
      {links.length > 0 ? (
        <div className="flex items-center justify-center gap-2 flex-wrap pb-1">
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
                <QuickLinkIcon link={link} />
              </a>
              <button
                className="absolute -left-1 -top-1 w-4 h-4 rounded-full bg-white border border-gray-200 text-gray-400 hover:text-brand-600 text-[10px] leading-none opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={() => startEdit(link)}
                title={`Edit ${link.title}`}
                aria-label={`Edit ${link.title}`}
              >
                ✎
              </button>
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
      detail: 'pending in Paperless / Paperless-GPT',
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
  const [settings, setSettings] = useState({});
  const [quickLinks, setQuickLinks] = useState([]);
  const [processingSummary, setProcessingSummary] = useState(null);
  const [refreshing, setRefreshing] = useState({});
  const [settingsSource, setSettingsSource] = useState(null);

  const loadDashboard = useCallback(async () => {
    const r = await apiFetch('/dashboard');
    if (r.ok) setDashboard(await r.json());
  }, [apiFetch]);

  const loadSettings = useCallback(async () => {
    const r = await apiFetch('/settings');
    if (!r.ok) return;
    const rows = await r.json();
    const map = {};
    rows.forEach((s) => { map[s.key] = s.value; });
    setSettings(map);
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
    loadSettings();
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
    await loadProcessingSummary();
    setRefreshing((p) => ({ ...p, [source]: false }));
  };

  const addQuickLink = async (form) => {
    await apiFetch('/quick-links', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        icon: form.icon || '🔗',
        sort_order: 0,
        is_active: true,
      }),
    });
    await loadQuickLinks();
  };

  const updateQuickLink = async (link, form) => {
    await apiFetch(`/quick-links/${link.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...link,
        ...form,
        icon: form.icon || '🔗',
        is_active: true,
      }),
    });
    await loadQuickLinks();
  };

  const deleteQuickLink = async (id) => {
    await apiFetch(`/quick-links/${id}`, { method: 'DELETE' });
    await loadQuickLinks();
  };

  const widgetSettingsFor = (source) => {
    const defaults = DEFAULT_WIDGET_SETTINGS[source] || {};
    if (source === 'paperless') {
      return {
        ...defaults,
        tag: settings['dashboard.paperless.tag'] || defaults.tag,
        limit: settings['dashboard.paperless.limit'] || defaults.limit,
      };
    }
    if (source === 'immich') {
      return {
        ...defaults,
        album_id: settings['dashboard.immich.album_id'] || defaults.album_id,
        limit: settings['dashboard.immich.limit'] || defaults.limit,
      };
    }
    if (source === 'jobber') {
      return {
        ...defaults,
        limit: settings['dashboard.jobber.limit'] || defaults.limit,
        show_client: settings['dashboard.jobber.show_client'] || defaults.show_client,
        show_status: settings['dashboard.jobber.show_status'] || defaults.show_status,
        show_date: settings['dashboard.jobber.show_date'] || defaults.show_date,
      };
    }
    return defaults;
  };

  const saveWidgetSettings = async (source, form) => {
    const entries = source === 'paperless'
      ? { 'dashboard.paperless.tag': form.tag || 'ai-processed', 'dashboard.paperless.limit': form.limit || '5' }
      : source === 'jobber'
        ? {
            'dashboard.jobber.limit': form.limit || '5',
            'dashboard.jobber.show_client': form.show_client || 'true',
            'dashboard.jobber.show_status': form.show_status || 'true',
            'dashboard.jobber.show_date': form.show_date || 'true',
          }
        : { 'dashboard.immich.album_id': form.album_id || '', 'dashboard.immich.limit': form.limit || '6' };
    for (const [key, value] of Object.entries(entries)) {
      await apiFetch(`/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value }) });
    }
    setSettingsSource(null);
    await loadSettings();
    await refreshSource(source);
  };

  if (!isLoggedIn) return <LoginForm />;

  const visibleQuickLinks = quickLinks.filter(
    (link) => link.is_active && link.title?.toLowerCase() !== 'actual budget'
  );

  return (
    <div className="p-6">
      {settingsSource && (
        <WidgetSettingsModal
          source={settingsSource}
          settings={widgetSettingsFor(settingsSource)}
          onClose={() => setSettingsSource(null)}
          onSave={saveWidgetSettings}
        />
      )}

      <QuickLinksWidget
        links={visibleQuickLinks}
        onAdd={addQuickLink}
        onUpdate={updateQuickLink}
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

      {/* Integration widgets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {SOURCES.map((src) => {
          const meta = SOURCE_META[src];
          const w = dashboard[src] || {};
          return (
            <WidgetCard
              key={src}
              source={src}
              title={meta.label}
              icon={meta.icon}
              status={w.status || 'unknown'}
              stale={w.stale}
              data={w.data || {}}
              settings={widgetSettingsFor(src)}
              onRefresh={() => refreshSource(src)}
              loading={refreshing[src]}
              onConfigure={['paperless', 'immich', 'jobber'].includes(src) ? () => setSettingsSource(src) : null}
            />
          );
        })}
      </div>

    </div>
  );
}
