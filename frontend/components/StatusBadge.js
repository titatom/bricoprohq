const COLORS = {
  ok: 'bg-green-100 text-green-800',
  active: 'bg-green-100 text-green-800',
  posted: 'bg-green-100 text-green-800',
  approved: 'bg-blue-100 text-blue-800',
  scheduled: 'bg-blue-100 text-blue-800',
  needs_review: 'bg-yellow-100 text-yellow-800',
  draft_generated: 'bg-yellow-100 text-yellow-800',
  idea: 'bg-purple-100 text-purple-800',
  new: 'bg-gray-100 text-gray-700',
  not_connected: 'bg-red-100 text-red-700',
  error: 'bg-red-100 text-red-700',
  archived: 'bg-gray-100 text-gray-500',
  reuse_later: 'bg-orange-100 text-orange-700',
  stale: 'bg-orange-100 text-orange-700',
  default: 'bg-gray-100 text-gray-600',
};

export default function StatusBadge({ status }) {
  const cls = COLORS[status] || COLORS.default;
  const label = status ? status.replace(/_/g, ' ') : '—';
  return (
    <span className={`badge ${cls}`}>{label}</span>
  );
}
