export type ActorRole = 'viewer' | 'adjuster' | 'underwriter' | 'claims_manager' | 'admin';

export interface ActorContext {
  email: string;
  role: ActorRole;
}

export interface HealthStatus {
  status: string;
  service: string;
  app_name: string;
  version: string;
  environment: string;
  llm_provider: string;
  database: string;
}

export interface OverviewSummary {
  policies_count: number;
  indexed_clauses_count: number;
  total_insured_limit: number;
  claims_count: number;
  total_recommended_reserves: number;
  siu_flagged_claims_count: number;
  verifications_count: number;
  excluded_or_ror_count: number;
  total_estimated_payout: number;
  submissions_count: number;
  avg_loss_ratio_pct: number;
  pending_approvals_count: number;
  audit_events_count: number;
  audit_chain_valid: boolean;
}

export interface PolicyClause {
  id: string;
  policy_id: string;
  clause_type: string;
  section_ref: string;
  page_number: number;
  title: string;
  clause_text: string;
  monetary_limit: number | null;
  deductible_override: number | null;
  keywords: string[];
}

export interface PolicySummary {
  id: string;
  policy_number: string;
  carrier_name: string;
  named_insured: string;
  insured_address: string;
  line_of_business: string;
  acord_form_type: string;
  effective_date: string;
  expiration_date: string;
  status: string;
  per_occurrence_limit: number;
  aggregate_limit: number;
  deductible: number;
  annual_premium: number;
  source_filename: string;
  extraction_confidence: number;
  clause_count: number;
  ai_summary: string;
  created_at: string;
}

export interface PolicyDetail extends PolicySummary {
  extracted_schedules: Array<Record<string, unknown>>;
  clauses: PolicyClause[];
}

export interface ClauseSearchResult {
  clause_id: string;
  policy_id: string;
  policy_number: string;
  named_insured: string;
  clause_type: string;
  section_ref: string;
  page_number: number;
  title: string;
  clause_text: string;
  monetary_limit: number | null;
  deductible_override: number | null;
  score: number;
  citation: string;
}

export interface FraudIndicator {
  code: string;
  severity: string;
  weight: number;
  message: string;
}

export interface ClaimItem {
  id: string;
  claim_number: string;
  policy_id: string | null;
  policy_number_reported: string;
  claimant_name: string;
  loss_date: string;
  reported_date: string;
  loss_location: string;
  peril_type: string;
  loss_description: string;
  claimed_amount: number;
  injuries_reported: boolean;
  police_report_filed: boolean;
  severity_tier: string;
  reserve_band: string;
  recommended_reserve: number;
  adjuster_queue: string;
  fraud_score: number;
  fraud_indicators: FraudIndicator[];
  triage_status: string;
  ai_triage_summary: string;
  llm_provider_used: string;
  approval_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MatchedClause {
  clause_id: string;
  clause_type: string;
  section_ref: string;
  page_number: number;
  title: string;
  score: number;
  monetary_limit: number | null;
  deductible_override: number | null;
  citation: string;
}

export interface TriggeredExclusion {
  clause_id: string | null;
  section_ref: string;
  page_number: number;
  title: string;
  overridden_by: string | null;
  citation: string;
}

export interface CoverageVerificationItem {
  id: string;
  claim_id: string;
  claim_number: string;
  policy_id: string;
  policy_number: string;
  determination: string;
  policy_in_force: boolean;
  applicable_limit: number;
  applicable_deductible: number;
  estimated_covered_payout: number;
  excess_over_limit: number;
  matched_clauses: MatchedClause[];
  triggered_exclusions: TriggeredExclusion[];
  citations: string[];
  confidence_score: number;
  requires_hitl_review: boolean;
  status: string;
  ai_rationale: string;
  llm_provider_used: string;
  approval_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LossRunEntry {
  loss_date: string;
  claim_number: string;
  peril: string;
  status: string;
  paid_amount: number;
  reserve_amount: number;
  incurred_amount?: number;
  description: string;
}

export interface RiskFactor {
  code: string;
  severity: string;
  factor: string;
  mitigation: string;
}

export interface UnderwritingSubmissionItem {
  id: string;
  submission_number: string;
  applicant_name: string;
  broker_name: string;
  line_of_business: string;
  requested_effective_date: string;
  requested_limit: number;
  requested_deductible: number;
  annual_revenue: number;
  tiv_amount: number;
  prior_premium: number;
  loss_history: LossRunEntry[];
  documents_submitted: string[];
  missing_documents: string[];
  completeness_score: number;
  total_incurred_losses: number;
  loss_count: number;
  loss_ratio_pct: number;
  risk_score: number;
  risk_tier: string;
  risk_factors: RiskFactor[];
  recommended_action: string;
  indicated_premium: number;
  status: string;
  ai_risk_brief: string;
  llm_provider_used: string;
  approval_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalRequestItem {
  id: string;
  entity_type: string;
  entity_id: string;
  action_requested: string;
  summary: string;
  financial_exposure: number;
  risk_level: string;
  status: string;
  requested_by: string;
  decided_by: string | null;
  decision_notes: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface AuditEventItem {
  id: string;
  sequence_no: number;
  event_type: string;
  actor_email: string;
  actor_role: string;
  entity_type: string;
  entity_id: string;
  action: string;
  details: Record<string, unknown>;
  prev_hash: string;
  event_hash: string;
  created_at: string;
}

export interface AuditChainVerify {
  valid: boolean;
  total_events: number;
  head_hash: string;
  broken_sequence_no: number | null;
  message: string;
}

export interface PiiRedactionFinding {
  category: string;
  count: number;
  placeholder: string;
}

export interface PiiRedactionResult {
  redacted_text: string;
  findings: PiiRedactionFinding[];
  total_redactions: number;
}
