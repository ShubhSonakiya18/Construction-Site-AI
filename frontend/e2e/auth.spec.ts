import { test, expect } from '@playwright/test'

// Sprint 18: codifies the login/logout flow every sprint from 9 onward has
// manually re-verified in a real browser (most recently as part of Sprint
// 15-17's client-role checks). Dev seed credentials, per
// docs/BACKEND_STARTUP.md section 4 -- DEVELOPMENT USE ONLY.
//
// This spec deliberately starts every test from a signed-out state
// (test.use({ storageState: ... } ) below overrides the chromium project's
// default authenticated storageState from auth.setup.ts) since these
// tests exercise the login form itself. Two real login calls total across
// this file (one success, one intentional failure) -- not one per test --
// to stay well inside app/core/config.py's rate_limit_login_attempts
// (10 per 5 minutes), the real limit that broke an earlier version of
// this suite when almost every spec logged in independently (see
// auth.setup.ts's own comment for the full story).
const ADMIN_EMAIL = 'admin@example.com'
const ADMIN_PASSWORD = 'Admin@123'

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('authentication', () => {
  test('redirects an unauthenticated visitor to /login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('heading', { name: 'Construction Site AI' })).toBeVisible()
  })

  test('shows an error on invalid credentials, then succeeds and logs out', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill(ADMIN_EMAIL)
    await page.getByLabel('Password').fill('wrong-password')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)

    // One real login call for this whole spec file -- reuses the same
    // page/form rather than a second beforeEach-driven attempt.
    await page.getByLabel('Password').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL('http://localhost:5173/')
    await expect(page.getByRole('heading', { name: 'Active project' })).toBeVisible()

    await page.getByRole('button', { name: 'Log out' }).click()
    await expect(page).toHaveURL(/\/login$/)
  })
})
