import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The app fetches its data with root-relative paths (`/data/...`). In dev
// the app is served by Vite while `data/` is served by a separate static
// server at the repo root (`python -m http.server 8765`) — a cross-origin
// fetch that `http.server` sends no CORS headers for. The proxy below
// makes the browser talk only to the Vite origin; Vite forwards `/data/*`
// to :8765, passing through HTTP Range / 206 so PMTiles + parquet range
// reads work in later phases. See _review/APP_REHAUL_PLAN.md "Dev server".
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/data': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
    },
  },
  // `vite preview` serves the built dist/ — a static server with no HMR
  // or file watcher, so it stays stable under a long test run. The E2E
  // suite runs against this (and it is the Phase D demo-serving model).
  preview: {
    port: 4173,
    strictPort: true,
    proxy: {
      '/data': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
    },
  },
  build: {
    // The bundle is MapLibre + DuckDB-WASM glue + the app in one chunk
    // (~360 kB gzipped). For a localhost-served tool that is a non-issue,
    // and the heavy DuckDB WASM binary is already a separate lazy asset.
    chunkSizeWarningLimit: 1600,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/lib/**/*.ts'],
      reporter: ['text', 'html'],
    },
  },
});
