import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The app fetches its data with root-relative paths (`/data/...`). In dev
// the app is served by Vite while `data/` is served by the repo-root
// range-capable static server (`python scripts/serve.py 8765`) — a
// cross-origin fetch the static server sends no CORS headers for. The proxy
// below makes the browser talk only to the Vite origin; Vite forwards
// `/data/*` to :8765, passing through HTTP Range / 206 so PMTiles + parquet
// range reads work. (Plain `python -m http.server` is not range-capable.)
export default defineConfig({
  plugins: [svelte()],
  // Under Vitest, resolve Svelte's *browser* (client) entry so component
  // tests can `mount()` in jsdom — Vitest processes modules in SSR mode by
  // default, which otherwise resolves the server build where `mount` throws.
  // Scoped to VITEST so the production build is untouched. (Svelte's official
  // Vitest recipe; avoids adding @testing-library.)
  resolve: process.env.VITEST ? { conditions: ['browser'] } : {},
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/data': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
      // Freshness snapshot (#235): prod serves the baked audit artifacts at
      // /audit/data/*; in dev the repo-root static server has the same files
      // under docs/research/data-audit/, so rewrite onto it.
      '/audit/data': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/audit\/data/, '/docs/research/data-audit'),
      },
      // Lead write-layer backend (uvicorn backend.app.main:app on :8000).
      '/api': {
        target: 'http://localhost:8000',
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
      // Freshness snapshot (#235): prod serves the baked audit artifacts at
      // /audit/data/*; in dev the repo-root static server has the same files
      // under docs/research/data-audit/, so rewrite onto it.
      '/audit/data': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/audit\/data/, '/docs/research/data-audit'),
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        // Split the heavy vendor libs into their own chunks (PERF-004) so an
        // app-code deploy no longer re-hashes (and busts the cache for) the
        // MapLibre + DuckDB bytes — and the browser can download vendor + app
        // in parallel. The app `index` chunk drops ~388 KB → ~51 KB gzip.
        // Function form (not the object form) — this build runs on Rolldown
        // (Vite 8), which only accepts a manualChunks function.
        manualChunks(id: string): string | undefined {
          if (id.includes('node_modules/maplibre-gl')) return 'maplibre';
          if (id.includes('node_modules/@duckdb/duckdb-wasm')) return 'duckdb';
          if (id.includes('node_modules/pmtiles')) return 'pmtiles';
          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.ts'],
    // Polyfills a no-op `Worker` so duckdb-wasm's browser build imports under
    // jsdom (the browser condition above pulls it in). See tests/setup.ts.
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/lib/**/*.ts'],
      reporter: ['text', 'html'],
    },
  },
});
