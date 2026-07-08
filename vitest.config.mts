import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/renderer/src/test-setup.ts'],
    css: false,
    include: ['src/renderer/src/**/*.test.{ts,tsx}'],

    // ── Memory & performance safeguards ─────────────────────────
    pool: 'forks',                     // runs tests in forked processes
    poolOptions: {
      forks: {
        singleTestPerProcess: true,    // each test in its own fork → memory isolation
      },
    },
    testTimeout: 30_000,               // kill tests hanging >30s
    hookTimeout: 15_000,               // timeouts for setup/teardown hooks
    maxConcurrency: 5,                 // limit simultaneous tests
    teardownTimeout: 10_000,           // clean up after each test file
    isolate: true,                     // fresh environment per test file
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer/src'),
    },
  },
})
