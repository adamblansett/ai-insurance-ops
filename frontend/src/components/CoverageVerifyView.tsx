import { CheckCircle2, FileSearch, Scale } from 'lucide-react';
import { useEffect, useState } from 'react';
import { decideApproval, runCoverageVerification } from '../api/client';
import type {
  ActorContext,
  ApprovalRequestItem,
  ClaimItem,
  CoverageVerificationItem,
  PolicySummary,
} from '../types/insurance';
import { StatusBadge, formatMoney } from './StatusBadge';

interface CoverageVerifyViewProps {
  actor: ActorContext;
  claims: ClaimItem[];
  policies: PolicySummary[];
  verifications: CoverageVerificationItem[];
  approvals: ApprovalRequestItem[];
  onRefresh: () => Promise<void>;
  onNotify: (msg: string, isError?: boolean) => void;
}

export function CoverageVerifyView({
  actor,
  claims,
  policies,
  verifications,
  approvals,
  onRefresh,
  onNotify,
}: CoverageVerifyViewProps) {
  const [selectedClaimId, setSelectedClaimId] = useState('');
  const [selectedPolicyId, setSelectedPolicyId] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!selectedClaimId && claims.length > 0) {
      setSelectedClaimId(claims[0].id);
    }
  }, [claims, selectedClaimId]);

  const approvalById = new Map(approvals.map((a) => [a.id, a]));

  async function handleRunVerify(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedClaimId) return;
    setBusy(true);
    try {
      const result = await runCoverageVerification(
        actor,
        selectedClaimId,
        selectedPolicyId || undefined,
      );
      onNotify(
        `Verified ${result.claim_number} against ${result.policy_number}: ${result.determination}.`,
      );
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Coverage verification failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveCoverage(approvalId: string, label: string) {
    setBusy(true);
    try {
      await decideApproval(actor, approvalId, 'approved', `Approved coverage memo for ${label}`);
      onNotify(`Approved coverage verification for ${label}.`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Approval failed', true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Scale className="h-4 w-4 text-indigo-600" />
          Run Citation-Grounded Coverage Verification
        </h2>
        <p className="mt-1 text-xs text-slate-600">
          Cross-checks FNOL claim facts against active policy periods, coverage grants,
          endorsement buy-backs, sublimits, deductibles, and exclusions.
        </p>

        <form onSubmit={handleRunVerify} className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">Select Claim</label>
            <select
              aria-label="Verification Claim"
              value={selectedClaimId}
              onChange={(e) => setSelectedClaimId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            >
              {claims.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.claim_number} — {c.peril_type} ({formatMoney(c.claimed_amount)})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">
              Policy Override (Optional)
            </label>
            <select
              aria-label="Verification Policy"
              value={selectedPolicyId}
              onChange={(e) => setSelectedPolicyId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            >
              <option value="">Auto-match reported policy</option>
              {policies.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.policy_number} — {p.named_insured}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={busy || !selectedClaimId}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <FileSearch className="h-3.5 w-3.5" />
              Run Coverage Verification
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        {verifications.map((ver) => {
          const pendingApp = ver.approval_id ? approvalById.get(ver.approval_id) : undefined;
          const canDecide = pendingApp && pendingApp.status === 'pending';
          return (
            <article
              key={ver.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-900">
                      {ver.claim_number} vs {ver.policy_number}
                    </h3>
                    <StatusBadge value={ver.determination} />
                    <StatusBadge value={ver.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    In Force: {ver.policy_in_force ? 'Yes' : 'No'} · Confidence{' '}
                    {Math.round(ver.confidence_score * 100)}%
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3 text-right text-xs">
                  <div>
                    <p className="text-[11px] text-slate-500">Applicable Limit</p>
                    <p className="font-semibold text-slate-900">
                      {formatMoney(ver.applicable_limit)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-500">Deductible</p>
                    <p className="font-semibold text-slate-900">
                      {formatMoney(ver.applicable_deductible)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-500">Est. Payout</p>
                    <p className="font-bold text-emerald-700">
                      {formatMoney(ver.estimated_covered_payout)}
                    </p>
                  </div>
                </div>
              </div>

              <p className="mt-3 text-xs leading-relaxed text-slate-700">{ver.ai_rationale}</p>

              <div className="mt-3 space-y-1.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Policy Page &amp; Section Citations
                </p>
                <div className="flex flex-wrap gap-2">
                  {ver.citations.map((cite) => (
                    <span
                      key={cite}
                      className="rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-medium text-indigo-800"
                    >
                      {cite}
                    </span>
                  ))}
                </div>
              </div>

              {ver.triggered_exclusions.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Exclusion Analysis
                  </p>
                  {ver.triggered_exclusions.map((ex, idx) => (
                    <div
                      key={`${ex.section_ref}-${idx}`}
                      className={`rounded-lg border px-3 py-2 text-xs ${
                        ex.overridden_by
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                          : 'border-rose-200 bg-rose-50 text-rose-900'
                      }`}
                    >
                      <span className="font-semibold">{ex.citation}</span>
                      {ex.overridden_by ? (
                        <span> — Overridden by {ex.overridden_by}</span>
                      ) : (
                        <span> — Exclusion applies</span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {canDecide && pendingApp && (
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleApproveCoverage(pendingApp.id, ver.claim_number)}
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approve Determination
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}
