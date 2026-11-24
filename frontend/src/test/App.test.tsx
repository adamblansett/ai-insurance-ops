import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  };
}

function buildApiMock() {
  const approvals = [
    {
      id: 'app-1',
      entity_type: 'claim_reserve',
      entity_id: 'clm-1',
      action_requested: 'approve_reserve_authority',
      summary: 'Reserve authority $85,000.00 for CLM-2026-5001 (water_damage)',
      financial_exposure: 85000,
      risk_level: 'medium',
      status: 'pending',
      requested_by: 'manager@acme-insops.local',
      decided_by: null,
      decision_notes: null,
      created_at: '2026-11-24T12:00:00Z',
      decided_at: null,
    },
  ];

  const policies = [
    {
      id: 'pol-1',
      policy_number: 'POL-CP-2026-1001',
      carrier_name: 'Beacon Commercial Indemnity',
      named_insured: 'Harborview Cold Storage LLC',
      insured_address: '420 Pier Ave, Portland, ME',
      line_of_business: 'commercial_property',
      acord_form_type: 'ACORD 140',
      effective_date: '2026-01-01',
      expiration_date: '2027-01-01',
      status: 'active',
      per_occurrence_limit: 2000000,
      aggregate_limit: 4000000,
      deductible: 5000,
      annual_premium: 48500,
      source_filename: 'harborview_acord_140.pdf',
      extraction_confidence: 0.98,
      clause_count: 5,
      ai_summary: 'Commercial property policy indexed.',
      created_at: '2026-11-24T12:00:00Z',
    },
  ];

  const claims = [
    {
      id: 'clm-1',
      claim_number: 'CLM-2026-5001',
      policy_id: 'pol-1',
      policy_number_reported: 'POL-CP-2026-1001',
      claimant_name: 'Harborview Cold Storage LLC',
      loss_date: '2026-08-14',
      reported_date: '2026-08-15',
      loss_location: 'Freezer Bay 3',
      peril_type: 'water_damage',
      loss_description: 'Burst overhead chilled-water pipe.',
      claimed_amount: 85000,
      injuries_reported: false,
      police_report_filed: false,
      severity_tier: 'high',
      reserve_band: 'complex_50k_250k',
      recommended_reserve: 85000,
      adjuster_queue: 'field_property',
      fraud_score: 0,
      fraud_indicators: [],
      triage_status: 'pending_reserve_approval',
      ai_triage_summary: 'Clean pipe burst claim.',
      llm_provider_used: 'mock',
      approval_id: 'app-1',
      created_at: '2026-11-24T12:00:00Z',
      updated_at: '2026-11-24T12:00:00Z',
    },
  ];

  const verifications = [
    {
      id: 'ver-1',
      claim_id: 'clm-1',
      claim_number: 'CLM-2026-5001',
      policy_id: 'pol-1',
      policy_number: 'POL-CP-2026-1001',
      determination: 'covered',
      policy_in_force: true,
      applicable_limit: 2000000,
      applicable_deductible: 5000,
      estimated_covered_payout: 80000,
      excess_over_limit: 0,
      matched_clauses: [],
      triggered_exclusions: [],
      citations: ['POL-CP-2026-1001 · Page 3 · Section I.B.3 — Burst Pipe Water Damage'],
      confidence_score: 0.94,
      requires_hitl_review: true,
      status: 'pending_review',
      ai_rationale: 'Covered under Section I.B.3 after $5,000 deductible.',
      llm_provider_used: 'mock',
      approval_id: null,
      created_at: '2026-11-24T12:00:00Z',
      updated_at: '2026-11-24T12:00:00Z',
    },
  ];

  const submissions = [
    {
      id: 'sub-1',
      submission_number: 'SUB-2026-8002',
      applicant_name: 'Northstar Logistics Warehouse Group',
      broker_name: 'Midwest Risk Partners',
      line_of_business: 'commercial_property',
      requested_effective_date: '2027-01-15',
      requested_limit: 2500000,
      requested_deductible: 10000,
      annual_revenue: 22000000,
      tiv_amount: 11000000,
      prior_premium: 50000,
      loss_history: [],
      documents_submitted: ['acord_125', 'acord_140', 'loss_runs_5yr'],
      missing_documents: ['statement_of_values', 'protective_safeguards'],
      completeness_score: 60,
      total_incurred_losses: 135000,
      loss_count: 3,
      loss_ratio_pct: 54,
      risk_score: 64,
      risk_tier: 'substandard',
      risk_factors: [],
      recommended_action: 'refer_senior_uw',
      indicated_premium: 64000,
      status: 'pending_uw_approval',
      ai_risk_brief: 'Missing protective safeguards and statement of values.',
      llm_provider_used: 'mock',
      approval_id: null,
      created_at: '2026-11-24T12:00:00Z',
      updated_at: '2026-11-24T12:00:00Z',
    },
  ];

  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();

    if (url === '/api/v1/health') {
      return jsonResponse({
        status: 'ok',
        service: 'ai-insurance-ops',
        app_name: 'AI Insurance Operations',
        version: '0.1.0',
        environment: 'test',
        llm_provider: 'mock',
        database: 'ok',
      });
    }
    if (url === '/api/v1/overview') {
      return jsonResponse({
        policies_count: 1,
        indexed_clauses_count: 5,
        total_insured_limit: 2000000,
        claims_count: 1,
        total_recommended_reserves: 85000,
        siu_flagged_claims_count: 0,
        verifications_count: 1,
        excluded_or_ror_count: 0,
        total_estimated_payout: 80000,
        submissions_count: 1,
        avg_loss_ratio_pct: 54,
        pending_approvals_count: 1,
        audit_events_count: 3,
        audit_chain_valid: true,
      });
    }
    if (url === '/api/v1/intake/policies') {
      return jsonResponse(policies);
    }
    if (url === '/api/v1/intake/policies/pol-1') {
      return jsonResponse({
        ...policies[0],
        extracted_schedules: [],
        clauses: [
          {
            id: 'cl-1',
            policy_id: 'pol-1',
            clause_type: 'coverage_grant',
            section_ref: 'Section I.B.3',
            page_number: 3,
            title: 'Burst Pipe Water Damage',
            clause_text: 'Covers accidental plumbing water discharge.',
            monetary_limit: 2000000,
            deductible_override: null,
            keywords: ['pipe', 'water'],
          },
        ],
      });
    }
    if (url === '/api/v1/claims') {
      return jsonResponse(claims);
    }
    if (url === '/api/v1/coverage/verifications') {
      return jsonResponse(verifications);
    }
    if (url === '/api/v1/coverage/verify' && init?.method === 'POST') {
      return jsonResponse(verifications[0], 201);
    }
    if (url === '/api/v1/underwriting/submissions') {
      return jsonResponse(submissions);
    }
    if (url === '/api/v1/audit/approvals') {
      return jsonResponse(approvals);
    }
    if (url === '/api/v1/audit/approvals/app-1/decide' && init?.method === 'POST') {
      approvals[0].status = 'approved';
      claims[0].triage_status = 'approved';
      return jsonResponse(approvals[0]);
    }
    if (url === '/api/v1/audit/events') {
      return jsonResponse([
        {
          id: 'ev-1',
          sequence_no: 1,
          event_type: 'seed.loaded',
          actor_email: 'manager@acme-insops.local',
          actor_role: 'claims_manager',
          entity_type: 'workspace',
          entity_id: 'demo-dataset',
          action: 'seeded',
          details: {},
          prev_hash: 'GENESIS',
          event_hash: 'abcdef1234567890abcdef1234567890',
          created_at: '2026-11-24T12:00:00Z',
        },
      ]);
    }
    if (url === '/api/v1/audit/events/verify') {
      return jsonResponse({
        valid: true,
        total_events: 1,
        head_hash: 'abcdef1234567890abcdef1234567890',
        broken_sequence_no: null,
        message: 'All 1 audit events verified intact.',
      });
    }
    if (url === '/api/v1/audit/pii/redact') {
      return jsonResponse({
        redacted_text:
          'Claimant Jane Doe (DOB [REDACTED_DOB], SSN [REDACTED_SSN], VIN [REDACTED_VIN]).',
        findings: [{ category: 'ssn', count: 1, placeholder: '[REDACTED_SSN]' }],
        total_redactions: 3,
      });
    }
    return jsonResponse({});
  });
}

describe('AI Insurance Operations workspace', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders live API health, overview KPIs, and navigates across all insurance workflows', async () => {
    const mockFetch = buildApiMock();
    vi.stubGlobal('fetch', mockFetch);

    render(<App />);

    expect(
      screen.getByRole('heading', { name: 'AI Insurance Operations' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/API Healthy \(mock\)/i)).toBeInTheDocument();
      expect(screen.getByText('$85,000.00')).toBeInTheDocument();
      expect(screen.getByText('Verified Intact')).toBeInTheDocument();
    });

    const nav = screen.getByRole('navigation', { name: 'Insurance Operations Modules' });

    // Navigate to Policy Intake and inspect indexed clause
    fireEvent.click(within(nav).getByRole('button', { name: /Policy Intake/i }));
    await waitFor(() => {
      expect(screen.getByText('POL-CP-2026-1001')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText(/Page 3 · Section I\.B\.3/i)).toBeInTheDocument();
    });

    // Navigate to Claims Triage and approve pending reserve gate
    fireEvent.click(within(nav).getByRole('button', { name: /Claims Triage/i }));
    await waitFor(() => {
      expect(screen.getByText('CLM-2026-5001')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Approve CLM-2026-5001/i }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/audit/approvals/app-1/decide',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    // Navigate to Coverage Verification, run verification, and verify page citation
    fireEvent.click(within(nav).getByRole('button', { name: /Coverage Verification/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/POL-CP-2026-1001 · Page 3 · Section I\.B\.3/i),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Run Coverage Verification/i }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/coverage/verify',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    // Navigate to Underwriting and check submission details
    fireEvent.click(within(nav).getByRole('button', { name: /Underwriting/i }));
    await waitFor(() => {
      expect(screen.getByText(/SUB-2026-8002/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Missing: protective_safeguards/i)).toBeInTheDocument();

    // Switch role to Adjuster, navigate to Audit & PII, and test redaction preview
    fireEvent.change(screen.getByLabelText('Actor Role'), { target: { value: 'adjuster' } });
    fireEvent.click(within(nav).getByRole('button', { name: /Audit & PII/i }));
    await waitFor(() => {
      expect(screen.getByText('seed.loaded')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Preview Cloud Redaction/i }));
    await waitFor(() => {
      expect(screen.getByText(/\[REDACTED_SSN\]/i)).toBeInTheDocument();
    });
  });
});
