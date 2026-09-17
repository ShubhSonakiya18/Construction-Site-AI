import { test, expect } from '@playwright/test'

// Sprint 18: codifies the RecordPage load check every sprint since 9 has
// manually re-verified. Deliberately does NOT exercise real microphone
// capture -- headless Chromium has no real microphone, and every prior
// manual verification of this page (per this project's own session
// history) has stopped at the same boundary: confirm the page loads and
// the Start Recording control is present, nothing more.
//
// Uses the chromium project's default storageState (an already-
// authenticated 'owner' session from auth.setup.ts) rather than logging
// in here -- see auth.setup.ts's comment for why.

test.describe('record page', () => {
  test('loads with the recording control visible for an upload-permitted role', async ({
    page,
  }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Active project' })).toBeVisible()

    await page.getByRole('link', { name: 'Record' }).click()
    await expect(page).toHaveURL(/\/record$/)
    await expect(page.getByRole('heading', { name: 'Record a site update' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Start Recording/ })).toBeVisible()
  })
})
