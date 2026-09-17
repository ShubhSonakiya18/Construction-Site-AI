import { test, expect, type APIRequestContext } from '@playwright/test'

// Sprint 18: codifies the client-role curation check Sprint 13 (ADR-056)
// established and every cost/safety-related sprint since (14, 15, 17) has
// manually re-run by hand in a real browser session. No client-role user is
// part of the seed data (database/seed/sample_data.py seeds only an
// 'owner' user) -- every prior manual verification created one ad-hoc via
// the real POST /api/v1/users endpoint, so this spec does the same thing
// as a real, repeatable setup step rather than assuming a fixture exists.
const ADMIN_EMAIL = 'admin@example.com'
const ADMIN_PASSWORD = 'Admin@123'
const API_BASE = 'http://127.0.0.1:8000/api/v1'

// Starts signed-out -- this spec logs in as a different (client-role) user
// than the chromium project's default authenticated storageState, so it
// must not inherit that state. See auth.setup.ts's comment on this
// project's real login rate limit (app/core/config.py's
// rate_limit_login_attempts) -- this spec makes exactly 2 real login
// calls total (one API call for the admin token used to create the
// client user, one browser-form login as that client user), not one per
// test.
test.use({ storageState: { cookies: [], origins: [] } })

async function loginForToken(request: APIRequestContext, email: string, password: string) {
  const response = await request.post(`${API_BASE}/auth/login`, {
    data: { email, password },
  })
  const body = await response.json()
  return body.data.access_token as string
}

test.describe('client-role analytics curation (ADR-056)', () => {
  let clientEmail: string
  let clientPassword: string

  test.beforeAll(async ({ playwright }) => {
    const request = await playwright.request.newContext()
    const adminToken = await loginForToken(request, ADMIN_EMAIL, ADMIN_PASSWORD)

    clientEmail = `e2e-client-${Date.now()}@example.com`
    clientPassword = 'E2eClient@123'

    const createResponse = await request.post(`${API_BASE}/users`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        email: clientEmail,
        password: clientPassword,
        first_name: 'E2E',
        last_name: 'Client',
        role: 'client',
      },
    })
    if (!createResponse.ok()) {
      throw new Error(
        `Failed to create e2e client-role user: ${createResponse.status()} ${await createResponse.text()}`,
      )
    }
    await request.dispose()
  })

  test('a client-role user does not see staff-only analytics sections', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill(clientEmail)
    await page.getByLabel('Password').fill(clientPassword)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { name: 'Active project' })).toBeVisible()

    await page.getByRole('combobox').first().selectOption({ index: 0 })

    // Visible to every role, per Sprint 10 Deliverable 6 / Sprint 13.
    await expect(page.getByRole('heading', { name: 'Completion trend' })).toBeVisible()

    // Staff-only per ADR-056/STAFF_ONLY_ANALYTICS_ROLES -- must NOT render
    // for a client-role user, matching every sprint since 13's own manual
    // check.
    await expect(page.getByRole('heading', { name: 'Cost and budget' })).not.toBeVisible()
    await expect(page.getByRole('heading', { name: 'Safety status' })).not.toBeVisible()
    await expect(
      page.getByRole('heading', { name: 'Reference cost estimate' }),
    ).not.toBeVisible()

    // No Record nav link either -- Permission.AUDIO_UPLOAD is not granted
    // to the client role (Sprint 10 Deliverable 7).
    await expect(page.getByRole('link', { name: 'Record' })).not.toBeVisible()
  })
})
