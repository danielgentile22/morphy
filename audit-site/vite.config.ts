import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { serveAuditData } from './vite/serve-audit-data';

// Deployed behind the existing auth at `/audit/` (a Caddy `handle /audit/*`
// block with the same forward_auth gate as `/data/processed/*`), so the build
// is base-pathed there. `serveAuditData` makes the live audit folder reachable
// at `<base>data/*` in dev + preview, matching the deployed Caddy route.
export default defineConfig({
  base: '/audit/',
  plugins: [svelte(), serveAuditData({ dir: '../docs/research/data-audit' })],
  // Under Vitest resolve Svelte's browser entry so components can mount in
  // jsdom (Vitest runs modules SSR-mode by default). Scoped to VITEST so the
  // production build is untouched — mirrors the app/ config.
  resolve: process.env.VITEST ? { conditions: ['browser'] } : {},
  // Distinct ports from the map app (5173/4173) so both can run at once. The
  // "Ask Claude" helper (PRD #188) calls the backend at `/api/*`; proxy it to
  // the local uvicorn (backend.app.main:app on :8000) so dev mirrors prod, where
  // Caddy reverse-proxies the same path. SSE passes through (no buffering).
  server: {
    port: 5273,
    strictPort: true,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  preview: {
    port: 4273,
    strictPort: true,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.ts'],
    coverage: { provider: 'v8', include: ['src/lib/**/*.ts'], reporter: ['text'] },
  },
});
