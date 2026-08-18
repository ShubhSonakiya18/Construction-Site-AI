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
  },
})
