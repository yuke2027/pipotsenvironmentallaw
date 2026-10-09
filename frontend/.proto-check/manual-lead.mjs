import { chromium } from '@playwright/test';
const BASE = 'http://manual-web';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await ctx.request.post(`${BASE}/api/v2/auth/login`, { data: { username: 'docshot', password: 'DocShot2026manual' } });
await page.goto(`${BASE}/leads`, { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);
// Create a pending lead via the page context (cookie + CSRF handled by api helper)
await page.evaluate(async () => {
  const csrf = document.cookie.split('; ').find(c => c.startsWith('esp_csrf='))?.slice(9);
  await fetch('/api/v2/leads', { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf || '') },
    body: JSON.stringify({ title: '朝阳区餐饮油烟在线监测异常核查', description: '群众举报反映望京片区餐饮油烟集中排放，夜间站点 PM2.5 与 CO 同步抬升，需现场核实净化设施运行情况。', priority: 'high' }) });
});
await page.goto(`${BASE}/leads`, { waitUntil: 'networkidle' });
await page.waitForTimeout(2200);
// 分派核查 modal
const assign = page.locator('button').filter({ hasText: '分派核查' }).first();
if (await assign.count()) { await assign.click(); await page.waitForTimeout(1500); }
await page.screenshot({ path: '/workspace/docs/system-manual/assets/m24-lead-assign.png', fullPage: true });
console.log('assign shot');
// close then 驳回
await page.keyboard.press('Escape'); await page.waitForTimeout(500);
const reject = page.locator('button').filter({ hasText: '驳回' }).first();
if (await reject.count()) { await reject.click(); await page.waitForTimeout(1300); }
await page.screenshot({ path: '/workspace/docs/system-manual/assets/m25-lead-reject.png', fullPage: true });
console.log('reject shot');
console.log('errors:', errors);
await browser.close();
