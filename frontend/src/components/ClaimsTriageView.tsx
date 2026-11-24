import { AlertTriangle, CheckCircle2, RefreshCw, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { createClaim, decideApproval, retriageClaim } from '../api/client';
import type { ActorContext, ApprovalRequestItem, ClaimItem } from '../types/insurance';
import { StatusBadge, formatMoney } from './StatusBadge';

interface ClaimsTriageViewProps {
  actor: ActorContext;
  claims: ClaimItem[];
  approvals: ApprovalRequestItem[];
  onRefresh: () => Promise<void>;
  onNotify: (msg: string, isError?: boolean) => void;
}

export function ClaimsTriageView({
  actor,
  claims,
  approvals,
  onRefresh,
  onNotify,
}: ClaimsTriageViewProps) {
  const [claimNumber, setClaimNumber] = useState('CLM-2026-6100');
  const [policyNumber, setPolicyNumber] = useState('POL-CP-2026-1001');
  const [claimantName, setClaimantName] = useState('Harborview Cold Storage LLC');
  const [perilType, setPerilType] = useState('water_damage');
  const [claimedAmount, setClaimedAmount] = useState('32000');
  const [lossDate, setLossDate] = useState('2026-09-10');
  const [reportedDate, setReportedDate] = useState('2026-09-11');
  const [description, setDescription] = useState(
    'Burst chilled-water pipe flooded cold storage aisle 4.',
  );
  const [busy, setBusy] = useState(false);

  const approvalById = new Map(approvals.map((a) => [a.id, a]));

  async function handleSubmitFnol(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const created = await createClaim(actor, {
        claim_number: claimNumber,
        policy_number_reported: policyNumber,
        claimant_name: claimantName,
        loss_date: lossDate,
        reported_date: reportedDate,
        loss_location: 'Primary Facility',
        peril_type: perilType,
        loss_description: description,
        claimed_amount: Number(claimedAmount) || 5000,
      });
      onNotify(
        `Triaged ${created.claim_number}: ${created.severity_tier} severity · ${created.adjuster_queue}`,
      );
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'FNOL submission failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handleRetriage(claimId: string) {
    setBusy(true);
    try {
      const updated = await retriageClaim(actor, claimId);
      onNotify(`Retriaged ${updated.claim_number} (${updated.triage_status}).`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Retriage failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveClaimGate(approvalId: string, label: string) {
    setBusy(true);
    try {
      await decideApproval(actor, approvalId, 'approved', `Approved ${label} in Claims Triage`);
      onNotify(`Approved gate for ${label}.`);
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
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          Submit FNOL Claim for Automated Triage &amp; Fraud Scoring
        </h2>
        <form onSubmit={handleSubmitFnol} className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">Claim Number</label>
            <input
              type="text"
              value={claimNumber}
              onChange={(e) => setClaimNumber(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">Policy Number</label>
            <input
              type="text"
              value={policyNumber}
              onChange={(e) => setPolicyNumber(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">Claimant Name</label>
            <input
              type="text"
              value={claimantName}
              onChange={(e) => setClaimantName(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">Peril Type</label>
            <select
              value={perilType}
              onChange={(e) => setPerilType(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            >
              <option value="water_damage">Water Damage</option>
              <option value="flood">Flood / Storm Surge</option>
              <option value="fire">Fire / Smoke</option>
              <option value="theft">Theft</option>
              <option value="cyber_ransomware">Cyber / Ransomware</option>
              <option value="bodily_injury">Bodily Injury</option>
              <option value="wind_hail">Wind / Hail</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600">
              Claimed Amount ($)
            </label>
            <input
              type="number"
              value={claimedAmount}
              onChange={(e) => setClaimedAmount(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">Loss Date</label>
              <input
                type="date"
                value={lossDate}
                onChange={(e) => setLossDate(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">Reported</label>
              <input
                type="date"
                value={reportedDate}
                onChange={(e) => setReportedDate(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
              />
            </div>
          </div>
          <div className="sm:col-span-2">
            <label className="block text-[11px] font-semibold text-slate-600">
              Loss Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
            />
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              Submit &amp; Triage FNOL
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-3">
        {claims.map((claim) => {
          const pendingApp =
            claim.approval_id ? approvalById.get(claim.approval_id) : undefined;
          const canDecide = pendingApp && pendingApp.status === 'pending';
          return (
            <article
              key={claim.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-900">{claim.claim_number}</h3>
                    <StatusBadge value={claim.severity_tier} />
                    <StatusBadge value={claim.adjuster_queue} />
                    <StatusBadge value={claim.triage_status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-600">
                    Policy {claim.policy_number_reported} · Claimant: {claim.claimant_name} · Loss{' '}
                    {claim.loss_date} (Reported {claim.reported_date})
                  </p>
                </div>

                <div className="text-right text-xs">
                  <p className="font-bold text-slate-900">
                    Reserve: {formatMoney(claim.recommended_reserve)}
                  </p>
                  <p className="text-slate-500">
                    Claimed {formatMoney(claim.claimed_amount)} · Band{' '}
                    {claim.reserve_band.replace(/_/g, ' ')}
                  </p>
                </div>
              </div>

              <p className="mt-2.5 text-xs leading-relaxed text-slate-700">
                {claim.loss_description}
              </p>

              <div className="mt-3 flex flex-wrap items-center gap-4 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                <div className="flex items-center gap-2">
                  <ShieldAlert
                    className={`h-4 w-4 ${
                      claim.fraud_score >= 0.6 ? 'text-rose-600' : 'text-slate-400'
                    }`}
                  />
                  <span className="font-semibold text-slate-700">
                    SIU Fraud Score: {Math.round(claim.fraud_score * 100)}%
                  </span>
                </div>
                <div className="h-2 w-28 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className={`h-full ${
                      claim.fraud_score >= 0.6
                        ? 'bg-rose-600'
                        : claim.fraud_score >= 0.3
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{ width: `${Math.round(claim.fraud_score * 100)}%` }}
                  />
                </div>
                <span className="text-[11px] text-slate-500">{claim.ai_triage_summary}</span>
              </div>

              {claim.fraud_indicators.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {claim.fraud_indicators.map((ind) => (
                    <span
                      key={ind.code}
                      className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] font-medium text-rose-800"
                    >
                      {ind.code}: {ind.message}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRetriage(claim.id)}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Retriage
                </button>
                {canDecide && pendingApp && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleApproveClaimGate(pendingApp.id, claim.claim_number)}
                    aria-label={`Approve ${claim.claim_number}`}
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approve {claim.claim_number}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </section>
    </div>
  );
}
