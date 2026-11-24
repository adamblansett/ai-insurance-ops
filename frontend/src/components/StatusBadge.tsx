const BADGE_CLASSES: Record<string, string> = {
  // Positive / approved / covered
  covered: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  approved: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  active: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  preferred: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  quote: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  quoted_ready: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  auto_verified: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  triaged: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  low: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  fast_track_desk: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  coverage_grant: 'border-emerald-200 bg-emerald-50 text-emerald-700',

  // Partial / caution / review / standard
  partial_coverage: 'border-amber-200 bg-amber-50 text-amber-800',
  reservation_of_rights: 'border-amber-200 bg-amber-50 text-amber-800',
  pending: 'border-amber-200 bg-amber-50 text-amber-800',
  pending_review: 'border-amber-200 bg-amber-50 text-amber-800',
  pending_reserve_approval: 'border-amber-200 bg-amber-50 text-amber-800',
  pending_uw_approval: 'border-amber-200 bg-amber-50 text-amber-800',
  medium: 'border-amber-200 bg-amber-50 text-amber-800',
  standard: 'border-sky-200 bg-sky-50 text-sky-700',
  quote_with_conditions: 'border-sky-200 bg-sky-50 text-sky-700',
  endorsement: 'border-indigo-200 bg-indigo-50 text-indigo-700',
  sublimit: 'border-indigo-200 bg-indigo-50 text-indigo-700',
  condition: 'border-slate-200 bg-slate-100 text-slate-700',

  // High-risk / excluded / SIU / decline
  excluded: 'border-rose-200 bg-rose-50 text-rose-700',
  policy_inactive: 'border-rose-200 bg-rose-50 text-rose-700',
  rejected: 'border-rose-200 bg-rose-50 text-rose-700',
  declined: 'border-rose-200 bg-rose-50 text-rose-700',
  decline: 'border-rose-200 bg-rose-50 text-rose-700',
  decline_recommended: 'border-rose-200 bg-rose-50 text-rose-700',
  siu_investigation: 'border-rose-200 bg-rose-50 text-rose-700',
  siu_referred: 'border-rose-200 bg-rose-50 text-rose-700',
  pending_siu_review: 'border-rose-200 bg-rose-50 text-rose-700',
  substandard: 'border-orange-200 bg-orange-50 text-orange-800',
  refer_senior_uw: 'border-orange-200 bg-orange-50 text-orange-800',
  high: 'border-orange-200 bg-orange-50 text-orange-800',
  critical: 'border-rose-300 bg-rose-100 text-rose-800',
  catastrophic: 'border-rose-300 bg-rose-100 text-rose-800',
  exclusion: 'border-rose-200 bg-rose-50 text-rose-700',
};

export function formatMoney(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

export function StatusBadge({ value }: { value: string }) {
  const norm = value.toLowerCase().trim();
  const cls =
    BADGE_CLASSES[norm] ?? 'border-slate-200 bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {value.replace(/_/g, ' ')}
    </span>
  );
}
