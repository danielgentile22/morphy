import { defineConfig, devices } from '@playwright/test';

// E2E runs against the real AR + MT composites, and against the *built*
// app served by `vite preview` (a static server — stable under a long
// run, unlike the HMR dev server). Playwright starts two servers: the
// range-capable static server for /data, and `vite preview` (which
// proxies /data -> :8765). The app only ever talks to the preview origin.
export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // The suite drives MapLibre (WebGL) + DuckDB-WASM + PMTiles in two
  // browsers; 2 workers keeps memory pressure low enough that WebKit does
  // not crash under load. retries: 1 catches a rare environmental hiccup.
  workers: 2,
  retries: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Headless Chromium needs the SwiftShader software-GL fallback
        // explicitly enabled, or MapLibre's WebGL shaders fail to compile.
        launchOptions: { args: ['--enable-unsafe-swiftshader'] },
      },
    },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: [
    {
      // Range-capable static server (python -m http.server is not — and
      // PMTiles / DuckDB-WASM need 206 Partial Content).
      command: 'python3 ../scripts/serve.py 8765',
      url: 'http://localhost:8765/data/processed/composite/index.json',
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      // Build the app, then serve dist/ with `vite preview`.
      command: 'npm run build && npm run preview',
      url: 'http://localhost:4173',
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
