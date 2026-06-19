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
  // Distinct ports from the map app (5173/4173) so both can run at once.
  server: { port: 5273, strictPort: true },
  preview: { port: 4273, strictPort: true },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.ts'],
    coverage: { provider: 'v8', include: ['src/lib/**/*.ts'], reporter: ['text'] },
  },
});
