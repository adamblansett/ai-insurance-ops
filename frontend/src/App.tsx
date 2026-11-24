import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Briefcase,
  Database,
  FileSearch,
  FileText,
  LayoutDashboard,
  ShieldCheck,
} from 'lucide-react';
import {
  fetchApprovals,
  fetchAuditEvents,
  fetchClaims,
  fetchCoverageVerifications,
  fetchHealth,
  fetchOverview,
  fetchPolicies,
  fetchSubmissions,
  seedDemoData,
  verifyAuditChain,
} from './api/client';
import { AuditPiiView } from './components/AuditPiiView';
import { ClaimsTriageView } from './components/ClaimsTriageView';
import { CoverageVerifyView } from './components/CoverageVerifyView';
import { OverviewView } from './components/OverviewView';
import { PolicyIntakeView } from './components/PolicyIntakeView';
import { UnderwritingView } from './components/UnderwritingView';
import type {
  ActorContext,
  ActorRole,
  ApprovalRequestItem,
  AuditChainVerify,
  AuditEventItem,
  ClaimItem,
  CoverageVerificationItem,
  HealthStatus,
  OverviewSummary,
  PolicySummary,
  UnderwritingSubmissionItem,
} from './types/insurance';

const NAV_TABS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'intake', label: 'Policy Intake', icon: FileText },
  { id: 'claims', label: 'Claims Triage', icon: AlertTriangle },
  { id: 'coverage', label: 'Coverage Verification', icon: FileSearch },
  { id: 'underwriting', label: 'Underwriting', icon: Briefcase },
  { id: 'audit', label: 'Audit & PII', icon: ShieldCheck },
] as const;

const ROLE_EMAILS: Record<string, string> = {
  claims_manager: 'manager@acme-insops.local',
  underwriter: 'uw@acme-insops.local',
  adjuster: 'adjuster@acme-insops.local',
  viewer: 'viewer@acme-insops.local',
};

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [actor, setActor] = useState<ActorContext>({
    email: 'manager@acme-insops.local',
    role: 'claims_manager',
  });
  const [banner, setBanner] = useState<{ text: string; isError: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const [overview, setOverview] = useState<OverviewSummary | null>(null);
  const [policies, setPolicies] = useState<PolicySummary[]>([]);
  const [claims, setClaims] = useState<ClaimItem[]>([]);
  const [verifications, setVerifications] = useState<CoverageVerificationItem[]>([]);
  const [submissions, setSubmissions] = useState<UnderwritingSubmissionItem[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequestItem[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [chainStatus, setChainStatus] = useState<AuditChainVerify | null>(null);

  const notify = useCallback((text: string, isError = false) => {
    setBanner({ text, isError });
  }, []);

  const refreshWorkspace = useCallback(async () => {
    try {
      const [ov, pols, clms, vers, subs, apps, evs, chain] = await Promise.all([
        fetchOverview(actor),
        fetchPolicies(actor),
        fetchClaims(actor),
        fetchCoverageVerifications(actor),
        fetchSubmissions(actor),
        fetchApprovals(actor),
        fetchAuditEvents(actor),
        verifyAuditChain(actor),
      ]);
      setOverview(ov);
      setPolicies(pols);
      setClaims(clms);
      setVerifications(vers);
      setSubmissions(subs);
      setApprovals(apps);
      setAuditEvents(evs);
      setChainStatus(chain);
    } catch {
      // Keep UI resilient during offline preview
    }
  }, [actor]);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const h = await fetchHealth();
        if (!cancelled) {
          setHealth(h);
          setOffline(false);
        }
        await refreshWorkspace();
      } catch {
        if (!cancelled) {
          setOffline(true);
        }
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [refreshWorkspace]);

  async function handleLoadDemo(reset = false) {
    setBusy(true);
    try {
      const res = await seedDemoData(actor, reset);
      notify(res.message);
      await refreshWorkspace();
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Demo seed failed', true);
    } finally {
      setBusy(false);
    }
  }

  function handleRoleChange(role: ActorRole) {
    const email = ROLE_EMAILS[role] || 'manager@acme-insops.local';
    setActor({ email, role });
    notify(`Switched active actor to ${email} (${role}).`);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
              Phase 1 — Core Professional &amp; Enterprise Operations
            </p>
            <h1 className="mt-0.5 text-xl font-bold tracking-tight text-slate-900">
              AI Insurance Operations
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <label className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700">
              <span>Role:</span>
              <select
                aria-label="Actor Role"
                value={actor.role}
                onChange={(e) => handleRoleChange(e.target.value as ActorRole)}
                className="bg-transparent font-semibold text-indigo-700 focus:outline-none"
              >
                <option value="claims_manager">Claims Manager</option>
                <option value="underwriter">Underwriter</option>
                <option value="adjuster">Adjuster</option>
                <option value="viewer">Viewer</option>
              </select>
            </label>

            <button
              type="button"
              onClick={() => handleLoadDemo(true)}
              disabled={busy || offline}
              className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
            >
              <Database className="h-3.5 w-3.5" />
              {busy ? 'Loading...' : 'Reset Demo Data'}
            </button>

            <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-xs font-medium">
              <Activity
                className={`h-3.5 w-3.5 ${
                  health?.status === 'ok'
                    ? 'text-emerald-600'
                    : offline
                    ? 'text-amber-600'
                    : 'text-slate-400'
                }`}
              />
              <span>
                {health?.status === 'ok'
                  ? `API Healthy (${health.llm_provider})`
                  : offline
                  ? 'Offline Starter Preview'
                  : 'Checking API...'}
              </span>
            </div>
          </div>
        </div>

        <nav
          aria-label="Insurance Operations Modules"
          className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-6 pb-2"
        >
          {NAV_TABS.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${
                  active
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-6 py-6">
        {banner && (
          <div
            role="status"
            className={`flex items-center justify-between rounded-xl border px-4 py-2.5 text-xs font-medium ${
              banner.isError
                ? 'border-rose-200 bg-rose-50 text-rose-800'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800'
            }`}
          >
            <span>{banner.text}</span>
            <button
              type="button"
              onClick={() => setBanner(null)}
              className="ml-4 text-xs underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {activeTab === 'overview' && (
          <OverviewView
            actor={actor}
            overview={overview}
            approvals={approvals}
            onNavigate={setActiveTab}
            onLoadDemo={() => handleLoadDemo(false)}
            onRefresh={refreshWorkspace}
            onNotify={notify}
            busy={busy}
          />
        )}

        {activeTab === 'intake' && (
          <PolicyIntakeView
            actor={actor}
            policies={policies}
            onRefresh={refreshWorkspace}
            onNotify={notify}
          />
        )}

        {activeTab === 'claims' && (
          <ClaimsTriageView
            actor={actor}
            claims={claims}
            approvals={approvals}
            onRefresh={refreshWorkspace}
            onNotify={notify}
          />
        )}

        {activeTab === 'coverage' && (
          <CoverageVerifyView
            actor={actor}
            claims={claims}
            policies={policies}
            verifications={verifications}
            approvals={approvals}
            onRefresh={refreshWorkspace}
            onNotify={notify}
          />
        )}

        {activeTab === 'underwriting' && (
          <UnderwritingView
            actor={actor}
            submissions={submissions}
            approvals={approvals}
            onRefresh={refreshWorkspace}
            onNotify={notify}
          />
        )}

        {activeTab === 'audit' && (
          <AuditPiiView
            actor={actor}
            approvals={approvals}
            events={auditEvents}
            chainStatus={chainStatus}
            onChainVerified={setChainStatus}
            onRefresh={refreshWorkspace}
            onNotify={notify}
          />
        )}
      </main>
    </div>
  );
}
