import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  Scale,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';
import { decideApproval } from '../api/client';
import type {
  ActorContext,
  ApprovalRequestItem,
  OverviewSummary,
} from '../types/insurance';
import { StatusBadge, formatMoney } from './StatusBadge';

interface OverviewViewProps {
  actor: ActorContext;
  overview: OverviewSummary | null;
  approvals: ApprovalRequestItem[];
  onNavigate: (tab: string) => void;
  onLoadDemo: () => void;
  onRefresh: () => Promise<void>;
  onNotify: (msg: string, isError?: boolean) => void;
  busy: boolean;
}

export function OverviewView({
  actor,
  overview,
  approvals,
  onNavigate,
  onLoadDemo,
  onRefresh,
  onNotify,
  busy,
}: OverviewViewProps) {
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const pendingApprovals = approvals.filter((a) => a.status === 'pending');

  async function handleDecision(id: string, decision: 'approved' | 'rejected') {
    setDecidingId(id);
    try {
      await decideApproval(actor, id, decision, `${decision} from Executive Overview`);
      onNotify(`Approval ${decision} (${id.slice(0, 8)}).`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Approval decision failed', true);
    } finally {
      setDecidingId(null);
    }
  }

  return (
    <div className="space-y-6">
      {overview && overview.policies_count === 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
          <div>
            <h2 className="text-sm font-semibold text-indigo-950">
              Workspace is empty — load the realistic insurance demo dataset
            </h2>
            <p className="mt-0.5 text-xs text-indigo-800">
              Populate 3 ACORD policies (13 indexed clauses), 4 FNOL claims, 4 citation-grounded
              coverage verifications, and 3 underwriting submissions.
            </p>
          </div>
          <button
            type="button"
            onClick={onLoadDemo}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            <Database className="h-3.5 w-3.5" />
            {busy ? 'Loading...' : 'Load Demo Data'}
          </button>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>Active Policies &amp; Clauses</span>
            <FileText className="h-4 w-4 text-indigo-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {overview ? overview.policies_count : 0} Policies
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {overview ? overview.indexed_clauses_count : 0} indexed clauses ·{' '}
            {formatMoney(overview?.total_insured_limit ?? 0)} limits
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>Recommended Reserves</span>
            <ShieldAlert className="h-4 w-4 text-amber-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatMoney(overview?.total_recommended_reserves ?? 0)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {overview?.claims_count ?? 0} FNOL claims · {overview?.siu_flagged_claims_count ?? 0}{' '}
            SIU flagged
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>Verified Coverage Payouts</span>
            <Scale className="h-4 w-4 text-emerald-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatMoney(overview?.total_estimated_payout ?? 0)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {overview?.verifications_count ?? 0} verified · {overview?.excluded_or_ror_count ?? 0}{' '}
            excluded / ROR
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>Audit Integrity &amp; Gates</span>
            <ClipboardCheck className="h-4 w-4 text-indigo-600" />
          </div>
          <p className="mt-2 text-lg font-bold text-slate-900">
            {overview?.audit_chain_valid ?? true ? 'Verified Intact' : 'Integrity Alert'}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {overview?.pending_approvals_count ?? pendingApprovals.length} pending HITL gates ·{' '}
            {overview?.audit_events_count ?? 0} audit events
          </p>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            id: 'intake',
            title: 'Policy Intake',
            desc: 'Parse ACORD/declaration PDFs and search clause embeddings with page citations.',
            icon: FileText,
          },
          {
            id: 'claims',
            title: 'Claims Triage',
            desc: 'Normalize FNOLs, size reserve bands, score SIU fraud cues, and route queues.',
            icon: AlertTriangle,
          },
          {
            id: 'coverage',
            title: 'Coverage Verification',
            desc: 'Match claims to grants, endorsements, sublimits, and exclusions with citations.',
            icon: FileSearch,
          },
          {
            id: 'underwriting',
            title: 'Underwriting Support',
            desc: 'Score submission completeness, 5-year loss ratios, risk tiers, and pricing.',
            icon: ClipboardCheck,
          },
        ].map((card) => {
          const Icon = card.icon;
          return (
            <button
              key={card.id}
              type="button"
              onClick={() => onNavigate(card.id)}
              className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-indigo-300 hover:shadow"
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Icon className="h-4 w-4 text-indigo-600" />
                {card.title}
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{card.desc}</p>
            </button>
          );
        })}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              Pending Human-in-the-Loop Approvals ({pendingApprovals.length})
            </h2>
            <p className="text-xs text-slate-500">
              High-exposure reserves, SIU referrals, excluded/ROR coverage memos, and underwriting
              referrals require reviewer sign-off.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate('audit')}
            className="text-xs font-semibold text-indigo-600 hover:underline"
          >
            View Full Queue &amp; Ledger
          </button>
        </div>

        {pendingApprovals.length === 0 ? (
          <p className="mt-4 rounded-lg border border-dashed border-slate-200 p-4 text-center text-xs text-slate-500">
            No pending HITL approvals. All gates are resolved.
          </p>
        ) : (
          <div className="mt-4 space-y-2.5">
            {pendingApprovals.map((app) => (
              <div
                key={app.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge value={app.entity_type} />
                    <StatusBadge value={app.risk_level} />
                    <span className="text-xs font-semibold text-slate-800">{app.summary}</span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Exposure: {formatMoney(app.financial_exposure)} · Requested by{' '}
                    {app.requested_by}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={decidingId === app.id}
                    onClick={() => handleDecision(app.id, 'approved')}
                    aria-label={`Approve ${app.summary}`}
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={decidingId === app.id}
                    onClick={() => handleDecision(app.id, 'rejected')}
                    aria-label={`Reject ${app.summary}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
