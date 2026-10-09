import { chromium } from '@playwright/test';
const BASE = 'http://manual-web';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await ctx.request.post(`${BASE}/api/v2/auth/login`, { data: { username: 'docshot', password: 'DocShot2026manual' } });
await page.goto(`${BASE}/forecasts`, { waitUntil: 'networkidle' });
await page.waitForTimeout(2500);
const b = page.locator('button').filter({ hasText: '运行预测' }).first();
if (await b.count()) { await b.click(); await page.waitForTimeout(4000); }
await page.screenshot({ path: '/workspace/docs/system-manual/assets/m35-forecast-job.png', fullPage: true });
console.log('errors:', errors);
await browser.close();
