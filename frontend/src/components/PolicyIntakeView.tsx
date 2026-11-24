import { FileText, Search, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  createPolicy,
  fetchPolicyDetail,
  searchClauses,
  uploadPolicyFile,
} from '../api/client';
import type {
  ActorContext,
  ClauseSearchResult,
  PolicyDetail,
  PolicySummary,
} from '../types/insurance';
import { StatusBadge, formatMoney } from './StatusBadge';

interface PolicyIntakeViewProps {
  actor: ActorContext;
  policies: PolicySummary[];
  onRefresh: () => Promise<void>;
  onNotify: (msg: string, isError?: boolean) => void;
}

export function PolicyIntakeView({
  actor,
  policies,
  onRefresh,
  onNotify,
}: PolicyIntakeViewProps) {
  const [selectedId, setSelectedId] = useState<string>('');
  const [detail, setDetail] = useState<PolicyDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ClauseSearchResult[]>([]);
  const [busy, setBusy] = useState(false);

  const [policyNumber, setPolicyNumber] = useState('POL-CP-2026-9901');
  const [namedInsured, setNamedInsured] = useState('Bayfront Marine Terminal LLC');
  const [lob, setLob] = useState('commercial_property');
  const [occLimit, setOccLimit] = useState('1500000');
  const [deductible, setDeductible] = useState('5000');

  useEffect(() => {
    if (!selectedId && policies.length > 0) {
      setSelectedId(policies[0].id);
    }
  }, [policies, selectedId]);

  useEffect(() => {
    let cancelled = false;
    async function loadDetail() {
      if (!selectedId) {
        setDetail(null);
        return;
      }
      try {
        const res = await fetchPolicyDetail(actor, selectedId);
        if (!cancelled) {
          setDetail(res);
        }
      } catch {
        // ignore transient error
      }
    }
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [actor, selectedId]);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const created = await uploadPolicyFile(actor, file);
      setSelectedId(created.id);
      setDetail(created);
      onNotify(`Ingested ${created.policy_number} (${created.clause_count} clauses).`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Policy upload failed', true);
    } finally {
      setBusy(false);
      e.target.value = '';
    }
  }

  async function handleQuickCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const limitVal = Number(occLimit) || 1000000;
      const dedVal = Number(deductible) || 5000;
      const created = await createPolicy(actor, {
        policy_number: policyNumber,
        named_insured: namedInsured,
        line_of_business: lob,
        acord_form_type: lob === 'cyber' ? 'ACORD 125' : 'ACORD 140',
        effective_date: '2026-01-01',
        expiration_date: '2027-01-01',
        per_occurrence_limit: limitVal,
        aggregate_limit: limitVal * 2,
        deductible: dedVal,
        annual_premium: 32000,
        clauses: [
          {
            clause_type: 'coverage_grant',
            section_ref: 'Section I.A',
            page_number: 1,
            title: 'Primary Insuring Agreement',
            clause_text: `Covers scheduled operations for ${namedInsured} up to $${limitVal.toLocaleString()}.`,
            monetary_limit: limitVal,
          },
          {
            clause_type: 'exclusion',
            section_ref: 'Exclusion B.1',
            page_number: 5,
            title: 'Flood and Surface Water Exclusion',
            clause_text: 'Excludes loss caused by flood, tidal surge, or surface water inundation.',
          },
        ],
      });
      setSelectedId(created.id);
      setDetail(created);
      onNotify(`Created policy ${created.policy_number}.`);
      await onRefresh();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Policy creation failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setBusy(true);
    try {
      const hits = await searchClauses(actor, searchQuery.trim());
      setSearchResults(hits);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Clause search failed', true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Upload className="h-4 w-4 text-indigo-600" />
            Upload ACORD / Declaration Policy (.pdf, .txt, .json)
          </h2>
          <p className="mt-1 text-xs text-slate-600">
            Extracts declarations metadata, schedules, and page-indexed coverage grants,
            endorsements, and exclusions.
          </p>
          <label className="mt-3 flex cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-xs font-semibold text-slate-700 hover:border-indigo-400 hover:bg-indigo-50">
            <span>{busy ? 'Indexing Document...' : 'Select Policy PDF / TXT / JSON'}</span>
            <input
              type="file"
              accept=".pdf,.txt,.json"
              onChange={handleFileUpload}
              disabled={busy}
              className="sr-only"
            />
          </label>

          <form onSubmit={handleSearch} className="mt-5 space-y-2">
            <label className="block text-xs font-semibold text-slate-700">
              Hybrid Vector &amp; Keyword Clause Search
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="e.g. water backup sublimit, ransomware 72 hours, flood exclusion"
                className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
              >
                <Search className="h-3.5 w-3.5" />
                Search Clauses
              </button>
            </div>
          </form>

          {searchResults.length > 0 && (
            <div className="mt-3 space-y-2">
              {searchResults.slice(0, 4).map((hit) => (
                <div
                  key={hit.clause_id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-indigo-700">{hit.citation}</span>
                    <StatusBadge value={hit.clause_type} />
                  </div>
                  <p className="mt-1 text-slate-600">{hit.clause_text}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <FileText className="h-4 w-4 text-indigo-600" />
            Quick Structured Policy Intake
          </h2>
          <form onSubmit={handleQuickCreate} className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Policy Number
              </label>
              <input
                type="text"
                value={policyNumber}
                onChange={(e) => setPolicyNumber(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Named Insured
              </label>
              <input
                type="text"
                value={namedInsured}
                onChange={(e) => setNamedInsured(e.target.value)}
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
                Per-Occurrence Limit ($)
              </label>
              <input
                type="number"
                value={occLimit}
                onChange={(e) => setOccLimit(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600">
                Deductible ($)
              </label>
              <input
                type="number"
                value={deductible}
                onChange={(e) => setDeductible(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                Ingest Policy
              </button>
            </div>
          </form>
        </section>
      </div>

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Ingested Policies ({policies.length})
          </h3>
          <div className="mt-3 space-y-2">
            {policies.map((pol) => (
              <button
                key={pol.id}
                type="button"
                onClick={() => setSelectedId(pol.id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selectedId === pol.id
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-slate-900">{pol.policy_number}</span>
                  <StatusBadge value={pol.status} />
                </div>
                <p className="mt-1 text-xs font-medium text-slate-700">{pol.named_insured}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  {pol.line_of_business.replace(/_/g, ' ')} · {pol.clause_count} clauses · Limit{' '}
                  {formatMoney(pol.per_occurrence_limit)}
                </p>
              </button>
            ))}
            {policies.length === 0 && (
              <p className="text-xs text-slate-500">No policies ingested yet.</p>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
          {detail ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-slate-900">{detail.policy_number}</h3>
                    <StatusBadge value={detail.status} />
                  </div>
                  <p className="text-xs text-slate-600">
                    {detail.named_insured} · {detail.carrier_name} ({detail.acord_form_type})
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    Term: {detail.effective_date} to {detail.expiration_date} · Confidence{' '}
                    {Math.round(detail.extraction_confidence * 100)}%
                  </p>
                </div>
                <div className="text-right text-xs">
                  <p className="font-semibold text-slate-800">
                    Limit: {formatMoney(detail.per_occurrence_limit)} / Agg{' '}
                    {formatMoney(detail.aggregate_limit)}
                  </p>
                  <p className="text-slate-500">
                    Deductible: {formatMoney(detail.deductible)} · Premium{' '}
                    {formatMoney(detail.annual_premium)}
                  </p>
                </div>
              </div>

              <div className="space-y-2.5">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Indexed Policy Clauses ({detail.clauses.length})
                </h4>
                {detail.clauses.map((clause) => (
                  <article
                    key={clause.id}
                    className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-slate-900">
                        Page {clause.page_number} · {clause.section_ref} — {clause.title}
                      </span>
                      <div className="flex items-center gap-2">
                        {clause.monetary_limit !== null && (
                          <span className="rounded bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 border border-slate-200">
                            Limit {formatMoney(clause.monetary_limit)}
                          </span>
                        )}
                        <StatusBadge value={clause.clause_type} />
                      </div>
                    </div>
                    <p className="mt-1.5 leading-relaxed text-slate-600">{clause.clause_text}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">Select a policy to inspect declarations and indexed clauses.</p>
          )}
        </div>
      </section>
    </div>
  );
}
