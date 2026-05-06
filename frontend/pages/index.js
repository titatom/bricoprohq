import { useEffect, useState, useCallback, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';

const SOURCES = ['google_calendar', 'jobber', 'immich', 'paperless', 'paperless-gpt'];
const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const DASHBOARD_LAYOUT_ORDER_KEY = 'dashboard.layout.order';
const DASHBOARD_LAYOUT_HIDDEN_KEY = 'dashboard.layout.hidden';

const SOURCE_META = {
  google_calendar: { label: 'Google Calendar', icon: '📅', logoDomain: 'calendar.google.com', color: 'brand' },
  jobber:          { label: 'Jobber',          icon: '🔧', logoDomain: 'jobber.com', color: 'brand' },
  immich:          { label: 'Immich / Photos', icon: '🖼️', logoDomain: 'immich.app', color: 'brand' },
  paperless:       { label: 'Paperless',       icon: '📄', logoDomain: 'docs.paperless-ngx.com', color: 'brand' },
  'paperless-gpt': { label: 'Paperless-GPT',   icon: '🤖', logoDomain: 'github.com', color: 'brand' },
};

const DEFAULT_DASHBOARD_ORDER = ['quick_links', ...SOURCES];

const DEFAULT_WIDGET_SETTINGS = {
  paperless: { tag: 'ai-processed', limit: '5' },
  immich: { album_id: '', limit: '6' },
  jobber: {
    limit: '5',
    show_jobs: 'true',
    show_requests: 'true',
    show_quotes: 'true',
    show_invoices: 'true',
    show_client: 'true',
    show_status: 'true',
    show_date: 'true',
    job_filter: 'upcoming',
    request_filter: 'new',
    invoice_filter: 'late,awaiting_payment',
  },
};

const DEFAULT_QUICK_LINKS = [
  { title: 'Jobber',               icon: 'link', url: 'https://app.jobber.com',              category: 'Operations' },
  { title: 'Google Calendar',      icon: 'link', url: 'https://calendar.google.com',          category: 'Operations' },
  { title: 'Gmail',                icon: 'link', url: 'https://mail.google.com',              category: 'Operations' },
  { title: 'Paperless-ngx',        icon: 'link', url: 'http://paperless.local',               category: 'Documents'  },
  { title: 'Immich',               icon: 'link', url: 'http://immich.local',                  category: 'Photos'     },
  { title: 'WordPress Admin',      icon: 'link', url: 'https://bricopro.ca/wp-admin',         category: 'Marketing'  },
  { title: 'Meta Business Suite',  icon: 'link', url: 'https://business.facebook.com',        category: 'Marketing'  },
  { title: 'Google Business',      icon: 'link', url: 'https://business.google.com',           category: 'Marketing'  },
  { title: 'Canva',                icon: 'link', url: 'https://canva.com',                    category: 'Marketing'  },
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

function initialsFor(text = '') {
  return String(text || 'Link')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'L';
}

function QuickLinkIcon({ link }) {
  const [failed, setFailed] = useState(false);
  const icon = (link.icon || '').trim();

  if (failed) {
    return (
      <span className="w-7 h-7 rounded-lg bg-brand-50 text-brand-700 text-xs font-bold flex items-center justify-center">
        {initialsFor(link.title)}
      </span>
    );
  }

  return (
    <img
      src={/^https?:\/\//i.test(icon) ? icon : logoUrlFor(link)}
      alt=""
      className="w-7 h-7 object-contain"
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
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
            <>
              <div className="grid grid-cols-1 gap-2 rounded-lg bg-gray-50 p-3">
                {[
                  ['show_jobs', 'Show jobs'],
                  ['show_requests', 'Show requests'],
                  ['show_quotes', 'Show quotes'],
                  ['show_invoices', 'Show invoices'],
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
              <div>
                <label className="label">Job filter</label>
                <select className="input" value={form.job_filter || 'upcoming'} onChange={(e) => setForm({ ...form, job_filter: e.target.value })}>
                  <option value="upcoming">Upcoming / Active</option>
                  <option value="unscheduled">Unscheduled</option>
                  <option value="late">Late</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
              <div>
                <label className="label">Request filter</label>
                <select className="input" value={form.request_filter || 'new'} onChange={(e) => setForm({ ...form, request_filter: e.target.value })}>
                  <option value="new">New only</option>
                  <option value="all">All pending</option>
                </select>
              </div>
              <div>
                <label className="label">Invoice filter</label>
                <select className="input" value={form.invoice_filter || 'late,awaiting_payment'} onChange={(e) => setForm({ ...form, invoice_filter: e.target.value })}>
                  <option value="late,awaiting_payment">Late + Awaiting payment</option>
                  <option value="late">Late only</option>
                  <option value="awaiting_payment">Awaiting payment only</option>
                  <option value="all">All pending</option>
                </select>
              </div>
            </>
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

function PaperlessWidget({ title, icon, status, stale, data, onRefresh, loading, onConfigure, isPaperlessGpt = false }) {
  const docs = isPaperlessGpt ? (data?.documents || []) : (data?.recent_documents || []);
  const stats = data?.stats || {};
  const health = data?.health || {};

  return (
    <div className="card flex flex-col gap-3">
      <WidgetHeader title={title} icon={icon} status={status} stale={stale} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />
      {status === 'not_connected' ? (
        <p className="text-sm text-red-500">Integration not connected. Configure in Settings.</p>
      ) : isPaperlessGpt ? (
        <div className="space-y-3">
          {health.service && (
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${health.ok ? 'bg-green-500' : 'bg-red-400'}`}></span>
              <span className="text-xs text-gray-500">{health.service} {health.ok ? 'online' : 'unreachable'}</span>
            </div>
          )}
          {Object.keys(stats).length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(stats).map(([key, value]) => (
                <div key={key} className="rounded-lg bg-gray-50 border border-gray-100 p-2.5">
                  <p className="text-xs text-gray-400 capitalize">{key.replace(/_/g, ' ')}</p>
                  <p className="text-lg font-bold text-gray-800">{typeof value === 'number' ? value : String(value)}</p>
                </div>
              ))}
            </div>
          )}
          {docs.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-400">{data?.count ?? docs.length} documents</p>
              {docs.slice(0, 3).map((doc) => (
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
          )}
          {!Object.keys(stats).length && docs.length === 0 && (
            <p className="text-sm text-gray-500">No data from Paperless-GPT yet.</p>
          )}
        </div>
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

function formatJobberStatus(value) {
  if (!value) return '';
  return String(value)
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatJobberDate(value, prefix = '') {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${prefix}${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}`;
}

function formatJobberMoney(value) {
  if (value === null || value === undefined || value === '') return '';

  if (typeof value === 'object') {
    const hasCents = value.cents !== null && value.cents !== undefined;
    const amount = hasCents ? Number(value.cents) / 100 : value.amount ?? value.value ?? value.total ?? value.balance;
    const currency = value.currency ?? value.currencyCode ?? value.currency_code;
    return formatJobberMoneyValue(amount, currency);
  }

  return formatJobberMoneyValue(value);
}

function formatJobberMoneyValue(amount, currency = 'CAD') {
  const numericAmount = Number(amount);
  if (!Number.isFinite(numericAmount)) return '';

  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(numericAmount);
  } catch {
    return `$${numericAmount.toFixed(2)}`;
  }
}

function jobberInvoiceAmount(item) {
  return (
    formatJobberMoney(item.amounts?.balance) ||
    formatJobberMoney(item.amounts?.total) ||
    formatJobberMoney(item.balance) ||
    formatJobberMoney(item.total)
  );
}

function jobberClientName(item) {
  return (
    item.client?.name ||
    item.clientName ||
    item.client_name ||
    item.contactName ||
    item.companyName ||
    ''
  );
}

function JobberWidget({ title, icon, status, stale, data, settings, onRefresh, loading, onConfigure }) {
  const limit = Math.max(1, Math.min(10, Number(settings?.limit || 5)));
  const sections = [
    {
      key: 'jobs',
      label: 'Upcoming jobs',
      items: data?.upcoming_jobs || [],
      enabled: settings?.show_jobs !== 'false',
      titleFor: (item) => item.title || 'Untitled job',
      statusFor: (item) => item.jobStatus,
      dateFor: (item) => item.startAt || item.startsAt || item.scheduledStartAt || item.start_at || item.start,
      dateLabel: 'Starts ',
      empty: 'No upcoming jobs.',
    },
    {
      key: 'requests',
      label: 'Pending requests',
      items: data?.pending_requests || [],
      enabled: settings?.show_requests !== 'false',
      titleFor: (item) => item.title || 'Untitled request',
      statusFor: (item) => item.requestStatus,
      dateFor: (item) => item.createdAt || item.created_at,
      dateLabel: 'Requested ',
      empty: 'No pending requests.',
    },
    {
      key: 'quotes',
      label: 'Pending quotes',
      items: data?.pending_quotes || [],
      enabled: settings?.show_quotes !== 'false',
      titleFor: (item) => item.title || 'Untitled quote',
      statusFor: (item) => item.quoteStatus,
      dateFor: (item) => item.createdAt || item.created_at,
      dateLabel: 'Created ',
      empty: 'No pending quotes.',
    },
    {
      key: 'invoices',
      label: 'Pending invoices',
      items: data?.pending_invoices || [],
      enabled: settings?.show_invoices !== 'false',
      titleFor: (item) => item.invoiceNumber ? `Invoice ${item.invoiceNumber}` : item.subject || item.title || 'Untitled invoice',
      statusFor: (item) => item.invoiceStatus,
      dateFor: (item) => item.dueDate || item.due_date || item.createdAt,
      dateLabel: 'Due ',
      amountFor: jobberInvoiceAmount,
      empty: 'No pending invoices.',
    },
  ].filter((section) => section.enabled);
  const hasItems = sections.some((section) => section.items.length > 0);

  return (
    <div className="card flex flex-col gap-3">
      <WidgetHeader title={title} icon={icon} status={status} stale={stale} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />
      {status === 'not_connected' ? (
        <p className="text-sm text-red-500">Integration not connected. Configure in Settings.</p>
      ) : data?.error ? (
        <p className="text-sm text-red-500">{data.error}</p>
      ) : hasItems ? (
        <div className="space-y-3">
          {sections.map((section) => {
            const visibleItems = section.items.slice(0, limit);
            if (visibleItems.length === 0) return null;
            return (
              <div key={section.key} className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{section.label}</h4>
                  <span className="text-xs text-gray-400">{section.items.length}</span>
                </div>
                {visibleItems.map((item, idx) => {
                  const clientName = jobberClientName(item);
                  const statusText = formatJobberStatus(section.statusFor(item));
                  const dateValue = section.dateFor(item);
                  const amountText = section.amountFor?.(item);
                  const href = item.jobberWebUri || item.jobber_web_uri;
                  const details = [
                    clientName,
                    statusText,
                    dateValue ? formatJobberDate(dateValue, section.dateLabel) : '',
                  ].filter(Boolean);
                  return (
                    <a
                      key={`${section.key}-${item.id || section.titleFor(item)}-${idx}`}
                      href={href || '#'}
                      target={href ? '_blank' : undefined}
                      rel={href ? 'noopener noreferrer' : undefined}
                      className="block rounded-lg border border-gray-100 p-3 bg-white hover:border-brand-200 hover:bg-brand-50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-medium text-sm text-gray-800">{section.titleFor(item)}</div>
                        {amountText && <div className="shrink-0 text-sm font-semibold text-gray-900">{amountText}</div>}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
                        {details.map((detail) => <span key={detail}>{detail}</span>)}
                      </div>
                    </a>
                  );
                })}
                {section.items.length > visibleItems.length && (
                  <p className="text-xs text-gray-400">{section.items.length - visibleItems.length} more {section.label.toLowerCase()} not shown.</p>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No Jobber items found.</p>
      )}
    </div>
  );
}

function WidgetCard({ source, title, icon, status, stale, data, settings, onRefresh, loading, onConfigure }) {
  if (source === 'jobber') {
    return <JobberWidget title={title} icon={icon} status={status} stale={stale} data={data} settings={settings} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} />;
  }
  if (source === 'paperless' || source === 'paperless-gpt') {
    return <PaperlessWidget title={title} icon={icon} status={status} stale={stale} data={data} onRefresh={onRefresh} loading={loading} onConfigure={onConfigure} isPaperlessGpt={source === 'paperless-gpt'} />;
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
      <input className="input w-28" placeholder="Logo URL" value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} />
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

function safeParseJson(value, fallback) {
  if (!value) return fallback;
  try {
    const parsed = JSON.parse(value);
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function dashboardCardTitle(cardId) {
  if (cardId === 'quick_links') return 'Quick Links';
  return SOURCE_META[cardId]?.label || cardId;
}

function normalizeDashboardOrder(rawOrder) {
  const parsed = safeParseJson(rawOrder, DEFAULT_DASHBOARD_ORDER);
  const order = Array.isArray(parsed) ? parsed : DEFAULT_DASHBOARD_ORDER;
  return [
    ...order.filter((id) => DEFAULT_DASHBOARD_ORDER.includes(id)),
    ...DEFAULT_DASHBOARD_ORDER.filter((id) => !order.includes(id)),
  ];
}

function normalizeDashboardHidden(rawHidden) {
  const parsed = safeParseJson(rawHidden, []);
  return new Set(Array.isArray(parsed) ? parsed.filter((id) => DEFAULT_DASHBOARD_ORDER.includes(id)) : []);
}

function DashboardStats({ dashboard, jobberStats }) {
  const integrationValues = SOURCES.map((src) => dashboard[src] || {});
  const connectedCount = integrationValues.filter((item) => item.status === 'ok').length;
  const staleCount = integrationValues.filter((item) => item.stale).length;
  const stats = [
    {
      label: 'Upcoming jobs',
      value: jobberStats.upcoming_unscheduled_count ?? 0,
      detail: 'unscheduled / action needed',
      secondary: jobberStats.action_required_count ? `${jobberStats.action_required_count} action required` : '',
    },
    {
      label: 'Open requests',
      value: jobberStats.new_requests_count ?? 0,
      detail: 'new requests to review',
    },
    {
      label: 'Pending invoices',
      value: jobberStats.pending_invoice_count ?? 0,
      detail: 'late + awaiting payment',
    },
    {
      label: 'Connected services',
      value: `${connectedCount}/${SOURCES.length}`,
      detail: staleCount ? `${staleCount} stale` : 'all current',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-6">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-2xl bg-white border border-gray-100 p-4 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{stat.label}</p>
          <p className="text-3xl font-black text-gray-900 mt-2">{stat.value}</p>
          <p className="text-xs text-gray-500 mt-1">{stat.detail}</p>
          {stat.secondary && <p className="text-xs text-orange-500 mt-0.5">{stat.secondary}</p>}
        </div>
      ))}
    </div>
  );
}

function DashboardCustomizePanel({ order, hidden, onMove, onToggle, onReset, onClose }) {
  return (
    <div className="card mb-6 border-l-4 border-accent-500">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="font-semibold text-gray-900">Customize dashboard</h3>
          <p className="text-sm text-gray-500 mt-0.5">Hide cards and choose the order that best matches your day-to-day view.</p>
        </div>
        <button className="text-sm text-gray-400 hover:text-gray-700" onClick={onClose}>Close</button>
      </div>
      <div className="space-y-2">
        {order.map((cardId, idx) => (
          <div key={cardId} className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
            <label className="flex flex-1 min-w-48 items-center gap-2 text-sm font-medium text-gray-700">
              <input
                type="checkbox"
                checked={!hidden.has(cardId)}
                onChange={() => onToggle(cardId)}
              />
              {dashboardCardTitle(cardId)}
            </label>
            <button className="btn-secondary text-xs py-1 px-2" onClick={() => onMove(cardId, -1)} disabled={idx === 0}>Up</button>
            <button className="btn-secondary text-xs py-1 px-2" onClick={() => onMove(cardId, 1)} disabled={idx === order.length - 1}>Down</button>
          </div>
        ))}
      </div>
      <button className="btn-secondary text-sm mt-4" onClick={onReset}>Reset dashboard</button>
    </div>
  );
}

export default function DashboardPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [dashboard, setDashboard] = useState({});
  const [settings, setSettings] = useState({});
  const [quickLinks, setQuickLinks] = useState([]);
  const [refreshing, setRefreshing] = useState({});
  const [settingsSource, setSettingsSource] = useState(null);
  const [customizing, setCustomizing] = useState(false);
  const [autoRefreshing, setAutoRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);
  const [jobberStats, setJobberStats] = useState({});
  const refreshAllInFlight = useRef(false);

  const loadDashboard = useCallback(async () => {
    const r = await apiFetch('/dashboard');
    if (r.ok) {
      setDashboard(await r.json());
      setLastRefreshedAt(new Date());
    }
  }, [apiFetch]);

  const loadJobberStats = useCallback(async () => {
    const r = await apiFetch('/dashboard/jobber-stats');
    if (r.ok) setJobberStats(await r.json());
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
    loadJobberStats();
    loadQuickLinks().then(async () => {
      const r = await apiFetch('/quick-links');
      if (r.ok) {
        const links = await r.json();
        if (links.length === 0) await seedLinks();
      }
    });
  }, [isLoggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshSource = useCallback(async (source) => {
    setRefreshing((p) => ({ ...p, [source]: true }));
    try {
      await apiFetch(`/dashboard/refresh/${source}`, { method: 'POST' });
      await loadDashboard();
    } finally {
      setRefreshing((p) => ({ ...p, [source]: false }));
    }
  }, [apiFetch, loadDashboard]);

  const refreshAll = useCallback(async ({ background = false } = {}) => {
    if (refreshAllInFlight.current) return;
    refreshAllInFlight.current = true;
    if (background) setAutoRefreshing(true);
    setRefreshing((prev) => ({
      ...prev,
      ...Object.fromEntries(SOURCES.map((source) => [source, true])),
    }));
    try {
      await Promise.all(SOURCES.map((source) => apiFetch(`/dashboard/refresh/${source}`, { method: 'POST' })));
      await Promise.all([loadDashboard(), loadJobberStats()]);
    } finally {
      refreshAllInFlight.current = false;
      setAutoRefreshing(false);
      setRefreshing((prev) => ({
        ...prev,
        ...Object.fromEntries(SOURCES.map((source) => [source, false])),
      }));
    }
  }, [apiFetch, loadDashboard, loadJobberStats]);

  useEffect(() => {
    if (!isLoggedIn) return;
    refreshAll({ background: true });
  }, [isLoggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isLoggedIn) return undefined;
    const interval = window.setInterval(() => {
      refreshAll({ background: true });
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [isLoggedIn, refreshAll]);

  const addQuickLink = async (form) => {
    await apiFetch('/quick-links', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        icon: form.icon || 'link',
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
        icon: form.icon || 'link',
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
        show_jobs: settings['dashboard.jobber.show_jobs'] || defaults.show_jobs,
        show_requests: settings['dashboard.jobber.show_requests'] || defaults.show_requests,
        show_quotes: settings['dashboard.jobber.show_quotes'] || defaults.show_quotes,
        show_invoices: settings['dashboard.jobber.show_invoices'] || defaults.show_invoices,
        job_filter: settings['dashboard.jobber.job_filter'] || defaults.job_filter,
        request_filter: settings['dashboard.jobber.request_filter'] || defaults.request_filter,
        invoice_filter: settings['dashboard.jobber.invoice_filter'] || defaults.invoice_filter,
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
            'dashboard.jobber.show_jobs': form.show_jobs || 'true',
            'dashboard.jobber.show_requests': form.show_requests || 'true',
            'dashboard.jobber.show_quotes': form.show_quotes || 'true',
            'dashboard.jobber.show_invoices': form.show_invoices || 'true',
            'dashboard.jobber.job_filter': form.job_filter || 'upcoming',
            'dashboard.jobber.request_filter': form.request_filter || 'new',
            'dashboard.jobber.invoice_filter': form.invoice_filter || 'late,awaiting_payment',
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
  const dashboardOrder = normalizeDashboardOrder(settings[DASHBOARD_LAYOUT_ORDER_KEY]);
  const hiddenCards = normalizeDashboardHidden(settings[DASHBOARD_LAYOUT_HIDDEN_KEY]);
  const visibleCards = dashboardOrder.filter((cardId) => !hiddenCards.has(cardId));

  const saveDashboardSetting = async (key, value) => {
    await apiFetch(`/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value }) });
    await loadSettings();
  };

  const moveDashboardCard = async (cardId, direction) => {
    const currentIndex = dashboardOrder.indexOf(cardId);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= dashboardOrder.length) return;
    const next = [...dashboardOrder];
    [next[currentIndex], next[nextIndex]] = [next[nextIndex], next[currentIndex]];
    await saveDashboardSetting(DASHBOARD_LAYOUT_ORDER_KEY, JSON.stringify(next));
  };

  const toggleDashboardCard = async (cardId) => {
    const next = new Set(hiddenCards);
    if (next.has(cardId)) next.delete(cardId);
    else next.add(cardId);
    await saveDashboardSetting(DASHBOARD_LAYOUT_HIDDEN_KEY, JSON.stringify([...next]));
  };

  const resetDashboardLayout = async () => {
    await saveDashboardSetting(DASHBOARD_LAYOUT_ORDER_KEY, JSON.stringify(DEFAULT_DASHBOARD_ORDER));
    await saveDashboardSetting(DASHBOARD_LAYOUT_HIDDEN_KEY, JSON.stringify([]));
  };

  const renderDashboardCard = (cardId) => {
    if (cardId === 'quick_links') {
      return (
        <QuickLinksWidget
          key={cardId}
          links={visibleQuickLinks}
          onAdd={addQuickLink}
          onUpdate={updateQuickLink}
          onDelete={deleteQuickLink}
        />
      );
    }
    const meta = SOURCE_META[cardId];
    if (!meta) return null;
    const w = dashboard[cardId] || {};
    return (
      <WidgetCard
        key={cardId}
        source={cardId}
        title={meta.label}
        icon={meta.icon}
        status={w.status || 'unknown'}
        stale={w.stale}
        data={w.data || {}}
        settings={widgetSettingsFor(cardId)}
        onRefresh={() => refreshSource(cardId)}
        loading={refreshing[cardId]}
        onConfigure={['paperless', 'immich', 'jobber'].includes(cardId) ? () => setSettingsSource(cardId) : null}
      />
    );
  };

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

      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Dashboard</h2>
          <p className="text-gray-500 text-sm mt-0.5">
            Business overview - auto-refreshes every {Math.round(AUTO_REFRESH_INTERVAL_MS / 60000)} minutes
            {lastRefreshedAt ? ` · last updated ${lastRefreshedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}
            {autoRefreshing ? ' · refreshing...' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => setCustomizing((value) => !value)}>
            {customizing ? 'Done' : 'Customize'}
          </button>
          <button className="btn-primary" onClick={() => refreshAll()}>
            Refresh All
          </button>
        </div>
      </div>

      {customizing && (
        <DashboardCustomizePanel
          order={dashboardOrder}
          hidden={hiddenCards}
          onMove={moveDashboardCard}
          onToggle={toggleDashboardCard}
          onReset={resetDashboardLayout}
          onClose={() => setCustomizing(false)}
        />
      )}

      <DashboardStats dashboard={dashboard} jobberStats={jobberStats} />

      {/* Integration widgets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {visibleCards.map(renderDashboardCard)}
      </div>

    </div>
  );
}
