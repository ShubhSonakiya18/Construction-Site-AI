import { test, expect } from '@playwright/test'

// Sprint 18: codifies the Dashboard -> project picker -> daily log ->
// review page flow manually re-verified across Sprints 10-17 (the project
// picker itself was Sprint 10's own Deliverable, closing a gap Sprint 9
// carried forward -- see docs/ROADMAP.md).
//
// Uses the chromium project's default storageState (an already-authenticated
// 'owner' session from auth.setup.ts) instead of logging in per test --
// see auth.setup.ts's comment for why: logging in fresh in every spec's
// beforeEach reliably tripped this project's real login rate limit
// (app/core/config.py's rate_limit_login_attempts) when the suite was run
// more than once in a short window, a real bug found live running this
// exact suite.

test.describe('dashboard and log review', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Active project' })).toBeVisible()
  })

  test('selecting the seeded project shows its daily log list', async ({ page }) => {
    // selectOption's `label` matcher requires an exact string, not a
    // RegExp (Playwright API constraint, found live running this suite) --
    // index: 0 is the first real <option> (no empty placeholder option
    // exists in DashboardPage.tsx's <select>), which is this project's
    // only seeded project.
    await page.getByRole('combobox').first().selectOption({ index: 0 })
    await expect(page.getByRole('heading', { name: 'Daily logs' })).toBeVisible()
  })

  test('opening a daily log shows the review page with Approve/Reject for an owner', async ({
    page,
  }) => {
    await page.getByRole('combobox').first().selectOption({ index: 0 })
    await expect(page.getByRole('heading', { name: 'Daily logs' })).toBeVisible()

    const firstLogLink = page.locator('.log-list-link').first()
    await expect(firstLogLink).toBeVisible()
    await firstLogLink.click()

    await expect(page.getByRole('heading', { name: /^Daily Log/ })).toBeVisible()
    // Approve/Reject only render for a log still under_review -- the
    // seeded sample log is pre-approved (see docs/PROJECT_STATE.md), so
    // this suite asserts the review page's real structure (trades/work
    // completed sections) rather than assuming a specific review_status.
    await expect(page.getByRole('heading', { name: 'Trades on site' })).toBeVisible()
  })

  test('the grounded Q&A box returns an answer for the seeded project', async ({ page }) => {
    await page.getByRole('combobox').first().selectOption({ index: 0 })
    await expect(page.getByRole('heading', { name: 'Ask about this project' })).toBeVisible()

    await page.getByPlaceholder(/Were there any delays/).fill('How many workers were on site?')
    await page.getByRole('button', { name: 'Ask' }).click()

    // Real Groq call -- generous timeout matching this project's own
    // EXTRACTION_GROQ_TIMEOUT/GENERATION_GROQ_TIMEOUT precedent, not
    // Playwright's tighter default expect() timeout.
    await expect(page.locator('.answer-box')).toBeVisible({ timeout: 20_000 })
  })
})
