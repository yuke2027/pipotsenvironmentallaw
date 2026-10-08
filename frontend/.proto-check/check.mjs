import { chromium } from '@playwright/test';

const base = process.env.BASE || 'http://host.docker.internal:5180/prototype/';
const browser = await chromium.launch();
const errors = [];
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });

async function shot(hash, name, prep) {
  await page.goto(base + hash);
  await page.waitForTimeout(1500);
  if (prep) await prep();
  await page.screenshot({ path: `/frontend/.proto-check/${name}.png`, fullPage: true });
}
await shot('#/', 'supervisor');
for (const role of ['执法人员', '研究者', '管理员']) {
  await shot('#/', role, async () => { await page.getByText(role, { exact: true }).click(); await page.waitForTimeout(1200); });
}
await shot('#/monitoring', 'monitoring', async () => { await page.getByText('监管主管', { exact: true }).click().catch(() => {}); });
await shot('#/stations/s01', 'station');
await shot('#/inspections/T-20261008-03', 'inspection');
await page.setViewportSize({ width: 1920, height: 1080 });
await shot('#/screen', 'screen');
console.log(JSON.stringify(errors, null, 2));
await browser.close();
