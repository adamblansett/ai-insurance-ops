import type {
  ActorContext,
  ApprovalRequestItem,
  AuditChainVerify,
  AuditEventItem,
  ClaimItem,
  ClauseSearchResult,
  CoverageVerificationItem,
  HealthStatus,
  IngestionJobItem,
  OverviewSummary,
  PiiRedactionResult,
  PolicyDetail,
  PolicySummary,
  UnderwritingSubmissionItem,
} from '../types/insurance';

async function apiFetch<T>(
  path: string,
  actor?: ActorContext,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (actor) {
    headers.set('X-Actor-Email', actor.email);
    headers.set('X-Actor-Role', actor.role);
  }
  if (init?.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody?.detail) {
        detail = errBody.detail;
      }
    } catch {
      // ignore non-JSON error body
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>('/api/v1/health');
}

export function fetchOverview(actor: ActorContext): Promise<OverviewSummary> {
  return apiFetch<OverviewSummary>('/api/v1/overview', actor);
}

export function seedDemoData(
  actor: ActorContext,
  reset = false,
): Promise<{ status: string; message: string }> {
  return apiFetch('/api/v1/seed/demo', actor, {
    method: 'POST',
    body: JSON.stringify({ reset }),
  });
}

export function fetchPolicies(actor: ActorContext): Promise<PolicySummary[]> {
  return apiFetch<PolicySummary[]>('/api/v1/intake/policies', actor);
}

export function fetchPolicyDetail(actor: ActorContext, policyId: string): Promise<PolicyDetail> {
  return apiFetch<PolicyDetail>(`/api/v1/intake/policies/${policyId}`, actor);
}

export function uploadPolicyFile(actor: ActorContext, file: File): Promise<PolicyDetail> {
  const form = new FormData();
  form.append('file', file);
  return apiFetch<PolicyDetail>('/api/v1/intake/policies/upload', actor, {
    method: 'POST',
    body: form,
  });
}

export function uploadPolicyFileAsync(
  actor: ActorContext,
  file: File,
): Promise<IngestionJobItem> {
  const form = new FormData();
  form.append('file', file);
  return apiFetch<IngestionJobItem>('/api/v1/intake/policies/upload-async', actor, {
    method: 'POST',
    body: form,
  });
}

export function fetchIngestionJobs(actor: ActorContext): Promise<IngestionJobItem[]> {
  return apiFetch<IngestionJobItem[]>('/api/v1/jobs', actor);
}

export function createPolicy(
  actor: ActorContext,
  payload: Record<string, unknown>,
): Promise<PolicyDetail> {
  return apiFetch<PolicyDetail>('/api/v1/intake/policies', actor, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function searchClauses(
  actor: ActorContext,
  query: string,
  policyId?: string,
): Promise<ClauseSearchResult[]> {
  return apiFetch<ClauseSearchResult[]>('/api/v1/intake/clauses/search', actor, {
    method: 'POST',
    body: JSON.stringify({ query, policy_id: policyId || null, limit: 12 }),
  });
}

export function fetchClaims(actor: ActorContext): Promise<ClaimItem[]> {
  return apiFetch<ClaimItem[]>('/api/v1/claims', actor);
}

export function createClaim(
  actor: ActorContext,
  payload: Record<string, unknown>,
): Promise<ClaimItem> {
  return apiFetch<ClaimItem>('/api/v1/claims', actor, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function retriageClaim(actor: ActorContext, claimId: string): Promise<ClaimItem> {
  return apiFetch<ClaimItem>(`/api/v1/claims/${claimId}/retriage`, actor, {
    method: 'POST',
  });
}

export function fetchCoverageVerifications(
  actor: ActorContext,
): Promise<CoverageVerificationItem[]> {
  return apiFetch<CoverageVerificationItem[]>('/api/v1/coverage/verifications', actor);
}

export function runCoverageVerification(
  actor: ActorContext,
  claimId: string,
  policyId?: string,
): Promise<CoverageVerificationItem> {
  return apiFetch<CoverageVerificationItem>('/api/v1/coverage/verify', actor, {
    method: 'POST',
    body: JSON.stringify({ claim_id: claimId, policy_id: policyId || null }),
  });
}

export function fetchSubmissions(actor: ActorContext): Promise<UnderwritingSubmissionItem[]> {
  return apiFetch<UnderwritingSubmissionItem[]>('/api/v1/underwriting/submissions', actor);
}

export function createSubmission(
  actor: ActorContext,
  payload: Record<string, unknown>,
): Promise<UnderwritingSubmissionItem> {
  return apiFetch<UnderwritingSubmissionItem>('/api/v1/underwriting/submissions', actor, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchApprovals(actor: ActorContext): Promise<ApprovalRequestItem[]> {
  return apiFetch<ApprovalRequestItem[]>('/api/v1/audit/approvals', actor);
}

export function decideApproval(
  actor: ActorContext,
  approvalId: string,
  decision: 'approved' | 'rejected',
  notes = '',
): Promise<ApprovalRequestItem> {
  return apiFetch<ApprovalRequestItem>(`/api/v1/audit/approvals/${approvalId}/decide`, actor, {
    method: 'POST',
    body: JSON.stringify({ decision, notes }),
  });
}

export function fetchAuditEvents(actor: ActorContext): Promise<AuditEventItem[]> {
  return apiFetch<AuditEventItem[]>('/api/v1/audit/events', actor);
}

export function verifyAuditChain(actor: ActorContext): Promise<AuditChainVerify> {
  return apiFetch<AuditChainVerify>('/api/v1/audit/events/verify', actor);
}

export function redactPiiPreview(
  actor: ActorContext,
  text: string,
): Promise<PiiRedactionResult> {
  return apiFetch<PiiRedactionResult>('/api/v1/audit/pii/redact', actor, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}
