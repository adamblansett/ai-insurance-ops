import { CheckCircle2, Lock, ShieldCheck, XCircle } from 'lucide-react';
import { useState } from 'react';
import { decideApproval, redactPiiPreview, verifyAuditChain } from '../api/client';
import type {
  ActorContext,
  ApprovalRequestItem,
  AuditChainVerify,
  AuditEventItem,
  PiiRedactionResult,
} from '../types/insurance';
import { StatusBadge, formatMoney } from './StatusBadge';

interface AuditPiiViewProps {
  actor: ActorContext;
  approvals: ApprovalRequestItem[];
  events: AuditEventItem[];
  chainStatus: AuditChainVerify | null;
  onChainVerified: (res: AuditChainVerify) => void;
  onRefresh: () => Promise<void>;
  onNotify: (msg: string, isError?: boolean) => void;
}

const DEFAULT_REDACTION_SAMPLE =
  'Claimant Jane Doe (DOB 1984-07-19, SSN 123-45-6789, DL D412-9988-11, Member ID MEM-884210) ' +
  'reported vehicle VIN 1HGCM82633A004352 loss via jane.doe@example.com or 555-234-5678.';

export function AuditPiiView({
  actor,
  approvals,
  events,
  chainStatus,
  onChainVerified,
  onRefresh,
  onNotify,
}: AuditPiiViewProps) {
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>(
    'all',
  );
  const [sampleText, setSampleText] = useState(DEFAULT_REDACTION_SAMPLE);
  const [redactionResult, setRedactionResult] = useState<PiiRedactionResult | null>(null);
  const [busy, setBusy] = useState(false);

  const visibleApprovals =
    statusFilter === 'all' ? approvals : approvals.filter((a) => a.status === statusFilter);

  async function handleVerifyChain() {
    setBusy(true);
    try {
      const res = await verifyAuditChain(actor);
      onChainVerified(res);
      onNotify(res.message, !res.valid);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Chain verification failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handleDecision(id: string, decision: 'approved' | 'rejected') {
    setBusy(true);
    try {
      await decideApproval(actor, id, decision, `${decision} via Audit & HITL Console`);
      onNotify(`Approval ${decision}.`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Approval decision failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handlePreviewRedaction() {
    setBusy(true);
    try {
      const res = await redactPiiPreview(actor, sampleText);
      setRedactionResult(res);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Redaction failed', true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              SHA-256 Immutable Audit Trail
            </h2>
            <p className="mt-1 text-xs text-slate-600">
              {chainStatus?.message ?? 'Every policy, claim, coverage, UW, and HITL decision is hash-chained.'}
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={handleVerifyChain}
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100"
          >
            Verify Chain Integrity
          </button>
        </div>

        <div className="mt-4 max-h-72 overflow-y-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 text-[11px] font-semibold uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Event</th>
                <th className="px-3 py-2">Actor</th>
                <th className="px-3 py-2">Entity</th>
                <th className="px-3 py-2">Event Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {events.map((ev) => (
                <tr key={ev.id}>
                  <td className="px-3 py-2 font-mono text-slate-600">{ev.sequence_no}</td>
                  <td className="px-3 py-2 font-semibold text-slate-900">{ev.event_type}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {ev.actor_email} ({ev.actor_role})
                  </td>
                  <td className="px-3 py-2 text-slate-600">
                    {ev.entity_type} · {ev.action}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
                    {ev.event_hash.slice(0, 14)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-900">
            HITL Approval Gate History ({visibleApprovals.length})
          </h2>
          <div className="flex gap-1.5">
            {(['all', 'pending', 'approved', 'rejected'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setStatusFilter(tab)}
                className={`rounded-full px-3 py-1 text-[11px] font-semibold capitalize ${
                  statusFilter === tab
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3 space-y-2.5">
          {visibleApprovals.map((app) => (
            <div
              key={app.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs"
            >
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge value={app.status} />
                  <StatusBadge value={app.entity_type} />
                  <span className="font-semibold text-slate-900">{app.summary}</span>
                </div>
                <p className="mt-1 text-slate-500">
                  Exposure: {formatMoney(app.financial_exposure)} · Requested by {app.requested_by}
                  {app.decided_by ? ` · Decided by ${app.decided_by}` : ''}
                </p>
              </div>
              {app.status === 'pending' && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleDecision(app.id, 'approved')}
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleDecision(app.id, 'rejected')}
                    className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2.5 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Reject
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Lock className="h-4 w-4 text-indigo-600" />
          Cloud LLM PII / PHI Redaction Sandbox
        </h2>
        <p className="mt-1 text-xs text-slate-600">
          Scrubs SSNs, FEINs, DOBs, Driver&apos;s Licenses, VINs, Member IDs, Emails, Phones, and
          Payment Cards before outbound cloud LLM requests.
        </p>
        <textarea
          rows={3}
          value={sampleText}
          onChange={(e) => setSampleText(e.target.value)}
          className="mt-3 w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:border-indigo-500 focus:outline-none"
        />
        <div className="mt-2.5 flex justify-end">
          <button
            type="button"
            disabled={busy}
            onClick={handlePreviewRedaction}
            className="rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
          >
            Preview Cloud Redaction
          </button>
        </div>

        {redactionResult && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs">
            <p className="font-semibold text-emerald-900">
              Scrubbed Output ({redactionResult.total_redactions} redactions):
            </p>
            <p className="mt-1 font-mono text-emerald-950">{redactionResult.redacted_text}</p>
          </div>
        )}
      </section>
    </div>
  );
}
