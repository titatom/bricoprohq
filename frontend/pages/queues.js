import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginForm from '../components/LoginForm';
import StatusBadge from '../components/StatusBadge';

const IMAGE_STATUSES = [
  'new', 'pending_ai', 'needs_review', 'business_photo', 'personal_photo',
  'trash_candidate', 'social_worthy', 'website_worthy', 'needs_client_approval',
  'used_in_content', 'do_not_publish',
];
const DOC_STATUSES = [
  'new', 'pending_ai', 'needs_review', 'business_receipt', 'personal_document',
  'missing_tags', 'missing_correspondent', 'missing_document_type', 'ready',
];
const IMAGE_SOURCES = ['immich', 'immich-gpt'];
const DOC_SOURCES   = ['paperless', 'paperless-gpt'];

function QueueTable({ items, onStatusChange, statusOptions, title, icon, emptyMsg }) {
  if (items.length === 0)
    return <p className="text-sm text-gray-400 py-6 text-center">{emptyMsg}</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
            <th className="pb-2 font-medium pr-4">Title</th>
            <th className="pb-2 font-medium pr-4">Source</th>
            <th className="pb-2 font-medium pr-4">Status</th>
            <th className="pb-2 font-medium pr-4">Note</th>
            <th className="pb-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50/50">
              <td className="py-2.5 pr-4 font-medium text-gray-800 max-w-xs truncate">
                {item.title || `#${item.id}`}
              </td>
              <td className="py-2.5 pr-4">
                <span className="badge bg-gray-100 text-gray-600">{item.source}</span>
              </td>
              <td className="py-2.5 pr-4">
                <StatusBadge status={item.status} />
              </td>
              <td className="py-2.5 pr-4 text-gray-400 text-xs max-w-xs truncate">
                {item.note || '—'}
              </td>
              <td className="py-2.5">
                <div className="flex items-center gap-2">
                  {item.url && (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-brand-600 hover:text-brand-800 text-xs underline"
                    >
                      Open ↗
                    </a>
                  )}
                  <select
                    className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                    value={item.status}
                    onChange={(e) => onStatusChange(item.id, e.target.value, item.note || '')}
                  >
                    {statusOptions.map((s) => (
                      <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AddAssetForm({ onAdd, defaultSource }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({
    title: '', source: defaultSource, source_url: '', service_category: '', status: 'new',
  });

  if (!show)
    return (
      <button className="btn-secondary text-xs py-1 px-3" onClick={() => setShow(true)}>
        + Add item
      </button>
    );

  return (
    <form
      className="flex flex-wrap gap-2 p-3 bg-gray-50 rounded-lg mb-3"
      onSubmit={(e) => { e.preventDefault(); onAdd(form); setShow(false); setForm({ title: '', source: defaultSource, source_url: '', service_category: '', status: 'new' }); }}
    >
      <input className="input flex-1 min-w-32" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
      <input className="input flex-1 min-w-48" placeholder="Source URL" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} />
      <input className="input w-40" placeholder="Category" value={form.service_category} onChange={(e) => setForm({ ...form, service_category: e.target.value })} />
      <button type="submit" className="btn-primary text-sm">Add</button>
      <button type="button" className="btn-secondary text-sm" onClick={() => setShow(false)}>Cancel</button>
    </form>
  );
}

export default function QueuesPage() {
  const { isLoggedIn, apiFetch } = useAuth();
  const [tab, setTab] = useState('images');
  const [images, setImages] = useState([]);
  const [docs, setDocs] = useState([]);
  const [imgStatus, setImgStatus] = useState('');
  const [imgSource, setImgSource] = useState('');
  const [docStatus, setDocStatus] = useState('');
  const [docSource, setDocSource] = useState('');

  const loadImages = useCallback(async () => {
    const params = new URLSearchParams();
    if (imgStatus) params.set('status', imgStatus);
    if (imgSource) params.set('source', imgSource);
    const r = await apiFetch(`/queues/images?${params}`);
    if (r.ok) setImages(await r.json());
  }, [apiFetch, imgStatus, imgSource]);

  const loadDocs = useCallback(async () => {
    const params = new URLSearchParams();
    if (docStatus) params.set('status', docStatus);
    if (docSource) params.set('source', docSource);
    const r = await apiFetch(`/queues/documents?${params}`);
    if (r.ok) setDocs(await r.json());
  }, [apiFetch, docStatus, docSource]);

  useEffect(() => { if (isLoggedIn) loadImages(); }, [isLoggedIn, imgStatus, imgSource]); // eslint-disable-line
  useEffect(() => { if (isLoggedIn) loadDocs(); }, [isLoggedIn, docStatus, docSource]); // eslint-disable-line

  const updateStatus = async (id, status, note) => {
    await apiFetch(`/queues/assets/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status, note }),
    });
    await loadImages(); await loadDocs();
  };

  const addAsset = async (form) => {
    await apiFetch('/queues/assets', {
      method: 'POST',
      body: JSON.stringify(form),
    });
    if (IMAGE_SOURCES.includes(form.source)) await loadImages();
    else await loadDocs();
  };

  if (!isLoggedIn) return <LoginForm />;

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Processing Queues</h2>
      <p className="text-gray-500 text-sm mb-6">Review pending photos and documents from Immich and Paperless.</p>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {[
          { key: 'images', label: `Images (${images.length})`, icon: '🖼️' },
          { key: 'documents', label: `Documents (${docs.length})`, icon: '📄' },
        ].map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              tab === key
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Image queue */}
      {tab === 'images' && (
        <div className="card">
          <div className="flex flex-wrap gap-2 items-center mb-4">
            <span className="text-sm font-medium text-gray-700">Filters:</span>
            <select className="select w-40" value={imgStatus} onChange={(e) => setImgStatus(e.target.value)}>
              <option value="">All statuses</option>
              {IMAGE_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
            <select className="select w-32" value={imgSource} onChange={(e) => setImgSource(e.target.value)}>
              <option value="">All sources</option>
              {IMAGE_SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button className="btn-secondary text-xs py-1 px-3" onClick={loadImages}>Reload</button>
            <div className="ml-auto">
              <AddAssetForm onAdd={addAsset} defaultSource="immich" />
            </div>
          </div>
          <QueueTable
            items={images}
            onStatusChange={updateStatus}
            statusOptions={IMAGE_STATUSES}
            title="Image Queue"
            icon="🖼️"
            emptyMsg="No images in queue. Add items or sync from Immich."
          />
        </div>
      )}

      {/* Document queue */}
      {tab === 'documents' && (
        <div className="card">
          <div className="flex flex-wrap gap-2 items-center mb-4">
            <span className="text-sm font-medium text-gray-700">Filters:</span>
            <select className="select w-40" value={docStatus} onChange={(e) => setDocStatus(e.target.value)}>
              <option value="">All statuses</option>
              {DOC_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
            <select className="select w-32" value={docSource} onChange={(e) => setDocSource(e.target.value)}>
              <option value="">All sources</option>
              {DOC_SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button className="btn-secondary text-xs py-1 px-3" onClick={loadDocs}>Reload</button>
            <div className="ml-auto">
              <AddAssetForm onAdd={addAsset} defaultSource="paperless" />
            </div>
          </div>
          <QueueTable
            items={docs}
            onStatusChange={updateStatus}
            statusOptions={DOC_STATUSES}
            title="Document Queue"
            icon="📄"
            emptyMsg="No documents in queue. Add items or sync from Paperless."
          />
        </div>
      )}
    </div>
  );
}
