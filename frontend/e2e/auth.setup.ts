import { test as setup, expect } from '@playwright/test'

// Sprint 18: authenticate ONCE via a real POST /api/v1/auth/login call and
// persist the result as Playwright storage state, reused by every spec
// that needs an authenticated 'owner' session.
//
// WHY THIS EXISTS (a real bug found running this suite live): the naive
// approach -- log in through the UI in every spec's beforeEach -- makes a
// real login call per test (auth.spec.ts alone has 3 login attempts,
// across the full suite it's 8+). app/core/config.py's
// rate_limit_login_attempts defaults to 10 per rate_limit_login_window_
// seconds (300s) -- a real, correct backend protection (Sprint 8,
// Subsystem 5), not a bug in the backend. Running this suite twice in a
// row, or once after manual dev testing against the same admin account,
// reliably tripped "Too many attempts. Please try again later." on the
// login page -- confirmed live via the actual failure screenshot before
// this fix. Authenticating once here keeps the suite's own real login
// calls to exactly 1 (plus a second, separate one for the client-role
// user client-role-curation.spec.ts creates), regardless of how many
// specs run.
const ADMIN_EMAIL = 'admin@example.com'
const ADMIN_PASSWORD = 'Admin@123'
const STORAGE_STATE_PATH = 'e2e/.auth/admin.json'

setup('authenticate as the seeded admin/owner user', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ADMIN_EMAIL)
  await page.getByLabel('Password').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Active project' })).toBeVisible()

  await page.context().storageState({ path: STORAGE_STATE_PATH })
})
