import { test, expect } from '@playwright/test';

const base = 'http://host.docker.internal:5180/prototype/';
const errors: string[] = [];
const findings: string[] = [];

test.beforeEach(({ page }) => {
  errors.length = 0;
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(`console: ${m.text()}`); });
});

test.afterEach(() => {
  expect(errors).toEqual([]);
});

test('交互走查', async ({ page }) => {
  const shot = (n: string) => page.screenshot({ path: `/proto/shots/w-${n}.png`, fullPage: true });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(base + '#/');
  await page.waitForTimeout(1500);

  // 1. 时间轴播放
  const t0 = await page.locator('.p-player-time').textContent();
  await page.locator('button[aria-label="播放 24 小时回放"]').click();
  await page.waitForTimeout(1800);
  const t1 = await page.locator('.p-player-time').textContent();
  findings.push(`时间轴播放: ${t0} -> ${t1} ${t0 !== t1 ? 'OK' : 'FAIL-未变化'}`);
  await page.locator('button[aria-label="播放 24 小时回放"]').click().catch(() => {});
  await shot('01-play');

  // 2. 地图悬停 tooltip
  const map = page.locator('.station-map').first();
  const box = await map.boundingBox();
  let tip = '';
  if (box) {
    outer: for (let y = box.y + 60; y < box.y + box.height - 20; y += 36)
      for (let x = box.x + 40; x < box.x + box.width - 30; x += 36) {
        await page.mouse.move(x, y);
        await page.waitForTimeout(60);
        const el = page.locator('.station-map div:has(> b)').filter({ hasText: 'AQI' }).last();
        if (await el.isVisible().catch(() => false)) { tip = (await el.textContent()) ?? ''; break outer; }
      }
  }
  findings.push(`地图悬停tooltip: ${tip ? 'OK ' + tip.replace(/\s+/g, ' ').slice(0, 60) : '未命中(坐标未对准)'}`);
  await shot('02-maptip');

  // 3. Ctrl+K 全局搜索
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(400);
  await page.keyboard.type('东四');
  await page.waitForTimeout(400);
  const hit = await page.locator('.p-palette-list button').count();
  findings.push(`Ctrl+K搜索"东四": ${hit} 条结果 ${hit > 0 ? 'OK' : 'FAIL'}`);
  await shot('03-search');
  await page.locator('.p-palette-list button').first().click();
  await page.waitForTimeout(1200);
  findings.push(`搜索跳转后URL: ${page.url().includes('stations') ? 'OK 到站点详情' : 'FAIL ' + page.url()}`);

  // 4. 站点详情切污染物
  await page.getByText('PM10', { exact: true }).last().click().catch(() => {});
  await page.waitForTimeout(800);
  await shot('04-station-pm10');

  // 5. 角色切换
  await page.goto(base + '#/');
  await page.getByText('执法人员', { exact: true }).click();
  await page.waitForTimeout(1200);
  findings.push(`执法人员首页: ${await page.locator('h1').first().textContent()}`);
  await shot('05-officer');
  await page.getByText('研究者', { exact: true }).click();
  await page.waitForTimeout(1200);
  const hasInsp = await page.locator('.ant-menu').getByText('核查与整改').count();
  findings.push(`研究者菜单隐藏监管组: ${hasInsp === 0 ? 'OK' : 'FAIL'}`);
  await shot('06-researcher');
  await page.getByText('监管主管', { exact: true }).click();
  await page.waitForTimeout(1000);

  // 6. 监测分析交互
  await page.goto(base + '#/monitoring');
  await page.waitForTimeout(1500);
  await page.locator('.p-filter .ant-select').first().click();
  await page.waitForTimeout(300);
  await page.locator('.ant-select-item').filter({ hasText: 'O3' }).first().click();
  await page.waitForTimeout(800);
  findings.push(`污染物切换O3: 图表标题=${await page.locator('.p-grid-map-chart .ant-card-head-title').last().textContent()}`);
  await page.locator('.p-filter .ant-switch').click();
  await page.waitForTimeout(500);
  await page.locator('.p-filter .ant-segmented-item').filter({ hasText: '日均' }).click();
  await page.waitForTimeout(800);
  await shot('07-monitoring-o3-day');
  await page.locator('.ant-tabs-tab').filter({ hasText: '热力矩阵' }).click();
  await page.waitForTimeout(1000);
  await shot('08-matrix');
  await page.locator('.ant-tabs-tab').filter({ hasText: '数据质量' }).click();
  await page.waitForTimeout(1000);
  await shot('09-quality');
  await page.locator('.ant-tabs-tab').filter({ hasText: '来源文件' }).click();
  await page.waitForTimeout(600);
  await shot('10-files');

  // 7. 核查详情
  await page.goto(base + '#/inspections/T-20261008-03');
  await page.waitForTimeout(1500);
  for (const tab of ['证据', '整改要求', '适用法规', '操作记录']) {
    await page.locator('.ant-tabs-tab').filter({ hasText: tab }).click().catch(() => {});
    await page.waitForTimeout(400);
  }
  await shot('11-inspection');

  // 8. 大屏回放走动
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(base + '#/screen');
  await page.waitForTimeout(2000);
  const s0 = await page.locator('.s-map-time b').textContent();
  await page.waitForTimeout(3000);
  const s1 = await page.locator('.s-map-time b').textContent();
  findings.push(`大屏回放: ${s0} -> ${s1} ${s0 !== s1 ? 'OK' : 'FAIL-未走动'}`);
  await shot('12-screen');

  // 9. 窄屏
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(base + '#/');
  await page.waitForTimeout(1200);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  findings.push(`1280宽横向溢出: ${overflow}px ${overflow <= 0 ? 'OK' : 'WARN'}`);
  await shot('13-1280');
  await page.setViewportSize({ width: 768, height: 1000 });
  await page.waitForTimeout(800);
  await shot('14-768');

  console.log('\n===== 走查结果 =====\n' + findings.map((f, i) => `${i + 1}. ${f}`).join('\n'));
});
