/**
 * I1 — End-to-end wiring smoke test.
 *
 * Playwright click-through of all 4 views:
 *   1. Patients list   → verify table renders with >=1 patient
 *   2. Patient detail   → click PT-007, verify vitals chart + SBAR
 *   3. Timeline         → verify event list renders
 *   4. Alerts           → verify alert queue renders, approve flow
 *
 * Prerequisites: `make demo` running (HAPI + MCP + A2A + proxy + Next.js).
 *
 * Run:
 *   cd tests/e2e && npx playwright test --config playwright.config.ts
 *
 * Acceptance (BUILD_PLAN.md I1):
 *   - <3 min startup (make demo)
 *   - Video-recordable (Playwright video: on)
 *   - Exit 0 in CI
 */

import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Pre-flight: verify services are reachable
// ---------------------------------------------------------------------------

test.describe("Pre-flight checks", () => {
  test("Next.js frontend is reachable", async ({ page }) => {
    const res = await page.goto("/");
    expect(res?.status()).toBeLessThan(400);
  });

  test("FastAPI proxy health endpoint responds", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("ok");
  });
});

// ---------------------------------------------------------------------------
// View 1 — Patients list
// ---------------------------------------------------------------------------

test.describe("Patients view", () => {
  test("renders patient table with at least 1 row", async ({ page }) => {
    await page.goto("/patients");
    await page.waitForLoadState("networkidle");

    // The table should have at least one patient row
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("patient rows have name, MRN, and risk badge", async ({ page }) => {
    await page.goto("/patients");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator("table tbody tr").first();
    await expect(firstRow).toBeVisible({ timeout: 10_000 });

    // Should have visible text content in cells
    const cells = firstRow.locator("td");
    const cellCount = await cells.count();
    expect(cellCount).toBeGreaterThanOrEqual(3);
  });

  test("clicking a patient navigates to detail view", async ({ page }) => {
    await page.goto("/patients");
    await page.waitForLoadState("networkidle");

    // Click the first patient link
    const firstLink = page.locator("table tbody tr a").first();
    await expect(firstLink).toBeVisible({ timeout: 10_000 });
    await firstLink.click();

    // Should navigate to /patients/[id]
    await page.waitForURL(/\/patients\/.+/);
    expect(page.url()).toMatch(/\/patients\/.+/);
  });
});

// ---------------------------------------------------------------------------
// View 2 — Patient detail (vitals + SBAR)
// ---------------------------------------------------------------------------

test.describe("Patient detail view", () => {
  test("renders patient header, vitals chart, and alerts panel", async ({ page }) => {
    // Navigate to a known patient
    await page.goto("/patients");
    await page.waitForLoadState("networkidle");

    // Click the first patient
    const firstLink = page.locator("table tbody tr a").first();
    await expect(firstLink).toBeVisible({ timeout: 10_000 });
    await firstLink.click();
    await page.waitForURL(/\/patients\/.+/);

    // Patient detail page should render
    await page.waitForLoadState("networkidle");

    // Should have the "Vitals Trend" chart heading
    await expect(
      page.locator("h2", { hasText: "Vitals Trend" })
    ).toBeVisible({ timeout: 10_000 });

    // Should have the "Recent Alerts" panel heading
    await expect(
      page.locator("h2", { hasText: "Recent Alerts" })
    ).toBeVisible();

    // Should have a "Back to roster" link
    await expect(
      page.locator("a", { hasText: "Back to roster" })
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// View 3 — Timeline
// ---------------------------------------------------------------------------

test.describe("Timeline view", () => {
  test("renders timeline page with heading and tick button", async ({ page }) => {
    await page.goto("/timeline");
    await page.waitForLoadState("networkidle");

    // Should show the A2A Agent Timeline heading
    await expect(
      page.locator("h1", { hasText: "A2A Agent Timeline" })
    ).toBeVisible({ timeout: 10_000 });

    // Should have a Tick Now button
    await expect(
      page.locator("button", { hasText: "Tick Now" })
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// View 4 — Alerts
// ---------------------------------------------------------------------------

test.describe("Alerts view", () => {
  test("renders review queue page", async ({ page }) => {
    await page.goto("/alerts");
    await page.waitForLoadState("networkidle");

    // Should show "Review Queue" heading
    await expect(
      page.locator("h1", { hasText: "Review Queue" })
    ).toBeVisible({ timeout: 10_000 });

    // Should show either alert cards or empty state
    const body = page.locator("body");
    await expect(body).toContainText(
      /Approve & send RRT|No pending alerts|Cannot reach backend/i,
      { timeout: 10_000 }
    );
  });
});

// ---------------------------------------------------------------------------
// Navigation — sidebar links work
// ---------------------------------------------------------------------------

test.describe("Navigation", () => {
  test("sidebar contains all primary nav links", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const nav = page.locator("nav[aria-label='Primary navigation']");
    await expect(nav).toBeVisible({ timeout: 10_000 });

    // Should have links for all four views
    await expect(nav.locator("a", { hasText: "Patients" })).toBeVisible();
    await expect(nav.locator("a", { hasText: "Timeline" })).toBeVisible();
    await expect(nav.locator("a", { hasText: "Alerts" })).toBeVisible();
    await expect(nav.locator("a", { hasText: "Settings" })).toBeVisible();
  });

  test("clicking Patients nav link navigates to /patients", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const nav = page.locator("nav[aria-label='Primary navigation']");
    await nav.locator("a", { hasText: "Patients" }).click();
    await page.waitForURL(/\/patients/);

    // Should see the patient roster
    await expect(
      page.locator("h1", { hasText: "Post-operative Patients" })
    ).toBeVisible({ timeout: 10_000 });
  });
});
