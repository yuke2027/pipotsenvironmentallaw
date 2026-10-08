import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.', timeout: 90000, workers: 1, reporter: 'list',
  use: { browserName: 'chromium', headless: true },
});
