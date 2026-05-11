import { useEffect, useState, useCallback } from 'react';
import Calendar from 'react-calendar';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';
import StatusBadge from '../components/StatusBadge';

const STATUSES = [
  'idea', 'draft_generated', 'needs_images', 'needs_review', 'approved',
  'scheduled', 'posted', 'reuse_later', 'turn_into_ad', 'turn_into_page', 'archived',
];

const PLATFORMS = ['facebook', 'instagram', 'gbp', 'linkedin', 'website', 'ad', 'email_sms'];

const KANBAN_COLS = [
  { key: 'idea',            label: 'Idea',           color: 'bg-purple-50 border-purple-200' },
  { key: 'draft_generated', label: 'Draft',          color: 'bg-yellow-50 border-yellow-200' },
  { key: 'needs_review',    label: 'Needs Review',   color: 'bg-orange-50 border-orange-200' },
  { key: 'approved',        label: 'Approved',       color: 'bg-brand-50 border-brand-200'   },
  { key: 'scheduled',       label: 'Scheduled',      color: 'bg-cyan-50 border-cyan-200'     },
  { key: 'posted',          label: 'Posted',         color: 'bg-green-50 border-green-200'   },
];

function copyDraftToClipboard(d) {
  const parts = [d.body || d.main_copy || '', d.hashtags, d.cta].filter(Boolean);
  const text = parts.join('\n\n');
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {});
    return true;
  }
  return false;
}

function DraftModal({ draft, onClose, onStatusChange, campaigns }) {
  const [status, setStatus] = useState(draft.status);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const save = async () => {
    setSaving(true);
    await onStatusChange(draft.id, status);
    setSaving(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <h3 className="font-semibold text-gray-900 text-lg">{draft.title}</h3>
          <button className="text-gray-400 hover:text-gray-600 text-xl leading-none" onClick={onClose}>×</button>
        </div>
        <div className="space-y-2 text-sm text-gray-600 mb-4">
          <div className="flex gap-4">
            <span><strong>Platform:</strong> {draft.platform}</span>
            <span><strong>Date:</strong> {draft.planned_date || '—'}</span>
          </div>
          {draft.campaign_id && <p><strong>Campaign:</strong> #{draft.campaign_id}</p>}
        </div>
        {draft.body && (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg text-sm text-gray-700 max-h-40 overflow-y-auto whitespace-pre-wrap">
            {draft.body}
          </div>
        )}
        <div className="mb-4">
          <label className="label">Move to status</label>
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            className="px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-700 text-sm font-medium hover:bg-gray-100 transition-colors"
            onClick={() => { if (copyDraftToClipboard(draft)) { setCopied(true); setTimeout(() => setCopied(false), 2000); } }}
          >
            {copied ? 'Copied!' : 'Copy to Clipboard'}
          </button>
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Update Status'}
          </button>
        </div>
      </div>
    </div>
  );
}

function KanbanBoard({ drafts, onStatusChange }) {
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
      {selected && (
        <DraftModal
          draft={selected}
          onClose={() => setSelected(null)}
          onStatusChange={onStatusChange}
        />
      )}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {KANBAN_COLS.map(({ key, label, color }) => (
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
                  <p className="text-sm font-medium text-gray-800 truncate">{d.title}</p>
                  <p className="text-xs text-gray-400 mt-1">{d.platform} {d.planned_date ? `· ${d.planned_date}` : ''}{d.planned_time ? ` ${d.planned_time}` : ''}</p>
                </div>
              ))}
              {(!grouped[key] || grouped[key].length === 0) && (
                <p className="text-xs text-gray-300 text-center py-4">Drop here</p>
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
                  {d.planned_time && <span className="text-xs text-gray-400">{d.planned_time}</span>}
                  <StatusBadge status={d.status} />
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

function ListView({ drafts, onStatusChange }) {
  const [copiedId, setCopiedId] = useState(null);

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
            {['Title', 'Platform', 'Status', 'Planned Date', 'Campaign', 'Actions', ''].map((h) => (
              <th key={`${h}-${Math.random()}`} className="pb-2 font-medium pr-4">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {drafts.map((d) => (
            <tr key={d.id} className="border-b border-gray-50 hover:bg-gray-50/50">
              <td className="py-2.5 pr-4 font-medium text-gray-800 max-w-xs truncate">{d.title}</td>
              <td className="py-2.5 pr-4"><span className="badge bg-gray-100 text-gray-600">{d.platform}</span></td>
              <td className="py-2.5 pr-4"><StatusBadge status={d.status} /></td>
              <td className="py-2.5 pr-4 text-gray-500">{d.planned_date || '—'}</td>
              <td className="py-2.5 pr-4 text-gray-400">{d.campaign_id ? `#${d.campaign_id}` : '—'}</td>
              <td className="py-2.5 pr-4">
                <select
                  className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                  value={d.status}
                  onChange={(e) => onStatusChange(d.id, e.target.value)}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </td>
              <td className="py-2.5">
                <button
                  className="text-xs text-gray-400 hover:text-brand-600 transition-colors"
                  onClick={() => handleCopy(d)}
                  title="Copy post to clipboard"
                >
                  {copiedId === d.id ? 'Copied!' : 'Copy'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {drafts.length === 0 && (
        <p className="text-sm text-gray-400 py-8 text-center">No drafts yet. Generate content in the AI Social Studio.</p>
      )}
    </div>
  );
}

export default function PublishingPage() {
  const { isLoggedIn, apiFetch } = useAuth();
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

  useEffect(() => { if (isLoggedIn) { loadDrafts(); loadCalendar(); } }, [isLoggedIn, filterPlatform, filterStatus]); // eslint-disable-line

  const updateStatus = async (id, status) => {
    await apiFetch(`/publishing/drafts/${id}/status?status=${status}`, { method: 'PUT' });
    await loadDrafts(); await loadCalendar();
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Publishing Queue</h2>
      <p className="text-gray-500 text-sm mb-6">Manage, schedule, and track your content across platforms.</p>

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center mb-4">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden">
          {[
            { key: 'kanban',   label: 'Kanban',   icon: '⬛' },
            { key: 'calendar', label: 'Calendar', icon: '📅' },
            { key: 'list',     label: 'List',     icon: '☰'  },
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
          {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="select w-40" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
        <button className="btn-secondary text-xs py-1.5 px-3" onClick={loadDrafts}>Reload</button>
        <span className="ml-auto text-sm text-gray-400">{drafts.length} draft{drafts.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Views */}
      <div className="card">
        {view === 'kanban'   && <KanbanBoard drafts={drafts} onStatusChange={updateStatus} />}
        {view === 'calendar' && <CalendarView drafts={calendar} />}
        {view === 'list'     && <ListView drafts={drafts} onStatusChange={updateStatus} />}
      </div>
    </div>
  );
}
