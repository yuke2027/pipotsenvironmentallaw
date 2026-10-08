import { test, expect } from '@playwright/test';

const base = process.env.PLAYWRIGHT_BASE_URL ?? 'http://host.docker.internal:5180/prototype/';
const errors: string[] = [];

test.beforeEach(({ page }) => {
  errors.length = 0;
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
});

test.afterEach(() => {
  expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

test('原型各页面渲染无错误', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  for (const [hash, name] of [['#/', 'supervisor'], ['#/monitoring', 'monitoring'], ['#/stations/s01', 'station'], ['#/inspections/T-20261008-03', 'inspection']] as const) {
    await page.goto(base + hash);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `/proto/shots/proto-${name}.png`, fullPage: true });
  }
  for (const role of ['执法人员', '研究者', '管理员']) {
    await page.goto(base + '#/');
    await page.getByText(role, { exact: true }).click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `/proto/shots/proto-${role}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(base + '#/screen');
  await page.waitForTimeout(1800);
  await page.screenshot({ path: '/proto/shots/proto-screen.png' });
});
