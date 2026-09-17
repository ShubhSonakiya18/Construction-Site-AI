/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Sprint 9 frontend core. Proxies /api to the FastAPI backend
// (docs/BACKEND_STARTUP.md) so the browser never makes a cross-origin
// request in dev — same-origin from the page's point of view, Vite
// forwards server-side. Backend's Settings.cors_allow_origins_raw
// defaults to "*" anyway (fine for local dev), but the proxy avoids
// relying on that and matches how this would work behind a real reverse
// proxy in production too.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    // Sprint 18: frontend/e2e/ holds real Playwright specs (`npm run
    // test:e2e`), a separate suite with its own `test`/`expect` globals
    // from @playwright/test -- vitest's default exclude list doesn't
    // cover a top-level e2e/ directory, so without this it tries to
    // collect and run those files itself and fails on the API mismatch
    // (found live running `npm run test` after adding frontend/e2e/).
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
})
