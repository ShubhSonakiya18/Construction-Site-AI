import { defineConfig, devices } from '@playwright/test'

// Sprint 18: a real, checked-in E2E suite replacing the ad-hoc, hand-written
// verification scripts every sprint from 9 through 17 relied on for "verified
// live in a real browser" claims. Drives the REAL Vite dev server + the real
// FastAPI backend -- neither is started by this config (see the "webServer"
// note below and docs/CONTRIBUTING.md's E2E section), matching how every
// prior manual verification actually worked: against processes already
// running per docs/BACKEND_STARTUP.md.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Reuse the single real login performed by auth.setup.ts (see
        // that file's comment for why -- a real backend rate limit,
        // ADR-041/Sprint 8, found live by running this suite twice in a
        // row). auth.spec.ts's own login/logout/invalid-credentials
        // tests intentionally start from a signed-out state regardless,
        // by clearing storage in their own setup.
        storageState: 'e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
      testIgnore: /auth\.setup\.ts/,
    },
  ],
  // Deliberately no `webServer` block: this suite assumes the real backend
  // (uvicorn, port 8000, per docs/BACKEND_STARTUP.md) and the real frontend
  // dev server (`npm run dev`, port 5173) are already running, the same
  // precondition every manual Playwright verification in this project's
  // history has always required. Auto-starting either here would mask a
  // real prerequisite instead of documenting it (see docs/CONTRIBUTING.md).
})
