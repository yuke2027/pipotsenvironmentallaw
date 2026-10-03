import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', timeout: 60000, fullyParallel: false, workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:8081', trace: 'retain-on-failure', screenshot: 'only-on-failure',
    browserName: 'chromium', headless: true },
  projects: [{ name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
             { name: 'tablet', use: { viewport: { width: 834, height: 1194 } } }],
});
