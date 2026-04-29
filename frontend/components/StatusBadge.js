// Status colour map — green = done/live, orange = action needed, navy = in-progress, gray = neutral/archived
const COLORS = {
  ok:               'bg-green-100 text-green-800',
  active:           'bg-green-100 text-green-800',
  posted:           'bg-green-100 text-green-800',
  ready:            'bg-green-100 text-green-800',
  approved:         'bg-brand-100 text-brand-700',
  scheduled:        'bg-brand-100 text-brand-700',
  needs_review:     'bg-accent-100 text-accent-700',
  draft_generated:  'bg-accent-100 text-accent-700',
  needs_images:     'bg-accent-100 text-accent-700',
  idea:             'bg-purple-100 text-purple-700',
  new:              'bg-gray-100 text-gray-600',
  not_connected:    'bg-red-100 text-red-700',
  error:            'bg-red-100 text-red-700',
  archived:         'bg-gray-100 text-gray-400',
  reuse_later:      'bg-accent-100 text-accent-700',
  stale:            'bg-accent-100 text-accent-700',
  social_worthy:    'bg-brand-100 text-brand-700',
  website_worthy:   'bg-brand-100 text-brand-700',
  business_photo:   'bg-brand-100 text-brand-700',
  default:          'bg-gray-100 text-gray-600',
};

export default function StatusBadge({ status }) {
  const cls = COLORS[status] || COLORS.default;
  const label = status ? status.replace(/_/g, ' ') : '—';
  return (
    <span className={`badge ${cls}`}>{label}</span>
  );
}
