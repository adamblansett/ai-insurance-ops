import { Briefcase, CheckCircle2, XCircle } from 'lucide-react';
import { useState } from 'react';
import { createSubmission, decideApproval } from '../api/client';
import type {
  ActorContext,
  ApprovalRequestItem,
  UnderwritingSubmissionItem,
} from '../types/insurance';
import { StatusBadge, formatMoney } from './StatusBadge';

interface UnderwritingViewProps {
  actor: ActorContext;
  submissions: UnderwritingSubmissionItem[];
  approvals: ApprovalRequestItem[];
  onRefresh: () => Promise<void>;
  onNotify: (msg: string, isError?: boolean) => void;
}

const DOC_OPTIONS = [
  'acord_125',
  'acord_140',
  'statement_of_values',
  'loss_runs_5yr',
  'protective_safeguards',
  'cyber_application',
  'mfa_attestation',
  'edr_backup_questionnaire',
  'loss_runs_3yr',
  'incident_response_plan',
];

export function UnderwritingView({
  actor,
  submissions,
  approvals,
  onRefresh,
  onNotify,
}: UnderwritingViewProps) {
  const [subNumber, setSubNumber] = useState('SUB-2026-8801');
  const [applicantName, setApplicantName] = useState('Pacific Timber Logistics LLC');
  const brokerName = 'Cascade Wholesale Brokers';
  const [lob, setLob] = useState('commercial_property');
  const [reqLimit, setReqLimit] = useState('1500000');
  const reqDeductible = '10000';
  const [priorPremium, setPriorPremium] = useState('45000');
  const [selectedDocs, setSelectedDocs] = useState<string[]>([
    'acord_125',
    'acord_140',
    'loss_runs_5yr',
  ]);
  const [lossAmount, setLossAmount] = useState('22000');
  const [busy, setBusy] = useState(false);

  const approvalById = new Map(approvals.map((a) => [a.id, a]));

  function toggleDoc(doc: string) {
    setSelectedDocs((prev) =>
      prev.includes(doc) ? prev.filter((item) => item !== doc) : [...prev, doc],
    );
  }

  async function handleCreateSubmission(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const incurred = Number(lossAmount) || 0;
      const created = await createSubmission(actor, {
        submission_number: subNumber,
        applicant_name: applicantName,
        broker_name: brokerName,
        line_of_business: lob,
        requested_effective_date: '2027-01-01',
        requested_limit: Number(reqLimit) || 1000000,
        requested_deductible: Number(reqDeductible) || 5000,
        annual_revenue: 12000000,
        tiv_amount: 7000000,
        prior_premium: Number(priorPremium) || 35000,
        documents_submitted: selectedDocs,
        loss_history:
          incurred > 0
            ? [
                {
                  loss_date: '2025-04-12',
                  claim_number: 'LR-NEW-01',
                  peril: 'water_damage',
                  status: 'closed',
                  paid_amount: incurred,
                  reserve_amount: 0,
                  description: 'Historical loss run entry.',
                },
              ]
            : [],
      });
      onNotify(
        `Analyzed ${created.submission_number}: ${created.risk_tier} (${created.recommended_action}).`,
      );
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Submission analysis failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handleUwDecision(
    approvalId: string,
    decision: 'approved' | 'rejected',
    subNum: string,
  ) {
    setBusy(true);
    try {
      await decideApproval(actor, approvalId, decision, `UW ${decision} for ${subNum}`);
      onNotify(`Underwriting gate ${decision} for ${subNum}.`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Decision failed', true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Briefcase className="h-4 w-4 text-indigo-600" />
          New Underwriting Submission &amp; Loss-Run Evaluation
        </h2>
        <form onSubmit={handleCreateSubmission} className="mt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Submission #
              </label>
              <input
                type="text"
                value={subNumber}
                onChange={(e) => setSubNumber(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Applicant Name
              </label>
              <input
                type="text"
                value={applicantName}
                onChange={(e) => setApplicantName(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Line of Business
              </label>
              <select
                value={lob}
                onChange={(e) => setLob(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              >
                <option value="commercial_property">Commercial Property</option>
                <option value="cyber">Cyber Liability</option>
                <option value="commercial_general_liability">General Liability</option>
                <option value="commercial_auto">Commercial Auto</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Requested Limit ($)
              </label>
              <input
                type="number"
                value={reqLimit}
                onChange={(e) => setReqLimit(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Prior Expiring Premium ($)
              </label>
              <input
                type="number"
                value={priorPremium}
                onChange={(e) => setPriorPremium(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Prior Incurred Losses ($)
              </label>
              <input
                type="number"
                value={lossAmount}
                onChange={(e) => setLossAmount(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
          </div>

          <div>
            <p className="text-[11px] font-semibold text-slate-600">Documents Submitted</p>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {DOC_OPTIONS.map((doc) => {
                const active = selectedDocs.includes(doc);
                return (
                  <button
                    key={doc}
                    type="button"
                    onClick={() => toggleDoc(doc)}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
                      active
                        ? 'border-indigo-500 bg-indigo-50 text-indigo-800'
                        : 'border-slate-200 bg-slate-50 text-slate-600'
                    }`}
                  >
                    {doc}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              Analyze Submission
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        {submissions.map((sub) => {
          const pendingApp = sub.approval_id ? approvalById.get(sub.approval_id) : undefined;
          const canDecide = pendingApp && pendingApp.status === 'pending';
          return (
            <article
              key={sub.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-900">
                      {sub.submission_number} — {sub.applicant_name}
                    </h3>
                    <StatusBadge value={sub.risk_tier} />
                    <StatusBadge value={sub.recommended_action} />
                    <StatusBadge value={sub.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-600">
                    {sub.line_of_business.replace(/_/g, ' ')} · Broker: {sub.broker_name || 'Direct'}{' '}
                    · Limit {formatMoney(sub.requested_limit)} · Deductible{' '}
                    {formatMoney(sub.requested_deductible)}
                  </p>
                </div>

                <div className="text-right text-xs">
                  <p className="font-bold text-slate-900">
                    Indicated Premium: {formatMoney(sub.indicated_premium)}
                  </p>
                  <p className="text-slate-500">
                    Loss Ratio: {sub.loss_ratio_pct.toFixed(1)}% ({sub.loss_count} losses,{' '}
                    {formatMoney(sub.total_incurred_losses)})
                  </p>
                </div>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
                  <div className="flex items-center justify-between font-semibold text-slate-700">
                    <span>Submission Completeness</span>
                    <span>{sub.completeness_score.toFixed(0)}%</span>
                  </div>
                  <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-200">
                    <div
                      className={`h-full ${
                        sub.completeness_score >= 80
                          ? 'bg-emerald-500'
                          : sub.completeness_score >= 50
                          ? 'bg-amber-500'
                          : 'bg-rose-500'
                      }`}
                      style={{ width: `${sub.completeness_score}%` }}
                    />
                  </div>
                  {sub.missing_documents.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {sub.missing_documents.map((doc) => (
                        <span
                          key={doc}
                          className="rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800"
                        >
                          Missing: {doc}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
                  <div className="flex items-center justify-between font-semibold text-slate-700">
                    <span>Composite Risk Score</span>
                    <span>{sub.risk_score.toFixed(1)} / 100</span>
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600">
                    {sub.ai_risk_brief}
                  </p>
                </div>
              </div>

              {sub.risk_factors.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  {sub.risk_factors.map((rf) => (
                    <div
                      key={rf.code}
                      className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
                    >
                      <span className="font-semibold text-slate-900">{rf.code}:</span>{' '}
                      <span className="text-slate-700">{rf.factor}</span>{' '}
                      <span className="text-indigo-700">Mitigation: {rf.mitigation}</span>
                    </div>
                  ))}
                </div>
              )}

              {canDecide && pendingApp && (
                <div className="mt-3 flex justify-end gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      handleUwDecision(pendingApp.id, 'approved', sub.submission_number)
                    }
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Confirm UW Decision
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      handleUwDecision(pendingApp.id, 'rejected', sub.submission_number)
                    }
                    className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Return for Revision
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
