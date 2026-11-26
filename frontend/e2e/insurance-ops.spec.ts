import { expect, test } from '@playwright/test';

test.describe('AI Insurance Operations live E2E workflow', () => {
  test('verifies overview KPIs, policy clause search, claims triage, coverage citations, underwriting, and audit redaction', async ({
    page,
  }) => {
    await page.goto('/');

    await expect(
      page.getByRole('heading', { name: 'AI Insurance Operations' }),
    ).toBeVisible();
    await expect(page.getByText(/API Healthy \(mock\)/i)).toBeVisible();
    await expect(page.getByText('3 Policies')).toBeVisible();
    await expect(page.getByText('Verified Intact')).toBeVisible();

    const nav = page.getByRole('navigation', {
      name: 'Insurance Operations Modules',
    });

    // 1. Policy Intake + Hybrid Clause Search
    await nav.getByRole('button', { name: /Policy Intake/i }).click();
    await page.getByRole('button', { name: /POL-CP-2026-1001/i }).click();
    await expect(
      page.getByRole('heading', { name: 'POL-CP-2026-1001' }),
    ).toBeVisible();
    await page
      .getByPlaceholder(/water backup sublimit/i)
      .fill('water backup sublimit');
    await page.getByRole('button', { name: /Search Clauses/i }).click();
    await expect(
      page.getByText(/POL-CP-2026-1001 · Page 12 · Endorsement CP 10 32/i).first(),
    ).toBeVisible();

    // 2. Claims Triage + FNOL submission + HITL approval
    await nav.getByRole('button', { name: /Claims Triage/i }).click();
    await expect(
      page.getByRole('heading', { name: 'CLM-2026-5001' }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'CLM-2026-5003' }),
    ).toBeVisible();

    const uniqueClaim = `CLM-E2E-${Date.now()}`;
    await page.locator('input[value="CLM-2026-6100"]').fill(uniqueClaim);
    await page.getByRole('button', { name: /Submit & Triage FNOL/i }).click();
    await expect(
      page.getByRole('heading', { name: uniqueClaim }),
    ).toBeVisible();

    // 3. Coverage Verification + Page/Section Citation Check
    await nav.getByRole('button', { name: /Coverage Verification/i }).click();
    await expect(
      page.getByText(/POL-CP-2026-1001 · Page 7 · Exclusion B\.1\.g/i).first(),
    ).toBeVisible();
    await page.getByRole('button', { name: /Run Coverage Verification/i }).click();
    await expect(page.getByRole('status')).toContainText(/Verified/i);

    // 4. Underwriting Support
    await nav.getByRole('button', { name: /Underwriting/i }).click();
    await expect(
      page.getByRole('heading', { name: /SUB-2026-8002/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: /SUB-2026-8003/i }),
    ).toBeVisible();

    // 5. Audit Ledger & Cloud PII/PHI Redaction Sandbox
    await nav.getByRole('button', { name: /Audit & PII/i }).click();
    await page.getByRole('button', { name: /Verify Chain Integrity/i }).click();
    await expect(page.getByRole('status')).toContainText(/verified intact/i);

    await page.getByRole('button', { name: /Preview Cloud Redaction/i }).click();
    await expect(page.getByText(/\[REDACTED_SSN\]/i).first()).toBeVisible();
    await expect(page.getByText(/\[REDACTED_VIN\]/i).first()).toBeVisible();
  });
});
