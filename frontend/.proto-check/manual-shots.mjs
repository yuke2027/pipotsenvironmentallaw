// Capture real-system screenshots for the architecture & function manual.
// Run inside mcr.microsoft.com/playwright image with repo mounted at /workspace:
//   docker run --rm --network environmental-platform_default -v <repo>:/workspace \
//     -w /workspace/docs/system-manual mcr.microsoft.com/playwright:v1.63.0-noble \
//     node capture.mjs
import { chromium } from '@playwright/test';

const BASE = process.env.BASE || 'http://host.docker.internal:8090';
const OUT = '/workspace/docs/system-manual/assets';
const INSPECTION = '63e229bc-1e10-49a2-814d-49ed0ef2e7ae';
const STATION = '98859dc0-28d2-4bf2-951e-57b543bf1b52'; // 东城东四
const ENTERPRISE = '5af533fa-987c-478d-b8b4-e7613be3a570'; // 燕山石化
const errors = [];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
page.on('pageerror', e => errors.push(`pageerror ${page.url()}: ${e.message}`));
page.on('console', m => { if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(`console ${page.url()}: ${m.text()}`); });

async function login(username, password) {
  // APIRequestContext sends no Origin header, which the server treats as a
  // non-browser request; the session cookie lands in the shared cookie jar.
  const res = await ctx.request.post(`${BASE}/api/v2/auth/login`, { data: { username, password } });
  if (!res.ok()) throw new Error(`login ${username} failed: ${res.status()} ${await res.text()}`);
}

async function shot(path, name, opts = {}) {
  await page.goto(BASE + path, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(opts.wait ?? 2500);
  if (opts.act) await opts.act();
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: opts.full ?? true });
  console.log('shot', name);
}

// 登录页（未登录态）
await shot('/login', 'm01-login', { wait: 1500 });

await login('docshot', 'DocShot2026manual');
await shot('/', 'm02-workspace-admin');
await shot('/monitoring', 'm03-monitoring', { act: async () => { await page.waitForTimeout(1000); } });
await shot(`/stations/${STATION}`, 'm04-station');
await shot('/evaluations', 'm05-evaluations');
await shot('/forecasts', 'm06-forecasts');
await shot('/leads', 'm07-leads');
await shot('/inspections', 'm08-inspections');
await shot('/enterprises', 'm09-enterprises');
await shot(`/enterprises/${ENTERPRISE}`, 'm10-enterprise-detail');
await shot('/models', 'm11-models');
await shot('/reports', 'm12-reports');
await shot('/admin', 'm13-admin');
// 数据源与许可页（管理后台的 sources 视图）
await shot('/admin?tab=sources', 'm14-admin-sources', { act: async () => {
  const tab = page.locator('.ant-tabs-tab').filter({ hasText: '数据源' }).first();
  if (await tab.count()) { await tab.click(); await page.waitForTimeout(1200); }
} });

// 执法人员视角（核查任务归属 + 我的工作台）
await login('liqiang', 'Officer2026pass');
await shot('/', 'm15-workspace-officer');
await shot(`/inspections/${INSPECTION}`, 'm16-inspection-detail');
await shot('/inspections', 'm17-inspections-officer');

// 研究者视角（监管菜单隐藏）
await login('zhaomin', 'Research2026pass');
await shot('/', 'm18-workspace-researcher');
await shot('/monitoring', 'm19-monitoring-researcher');

// 领导大屏为原型设计稿阶段，另行截取原型页面（标注"原型示意"）
console.log('errors:', JSON.stringify(errors, null, 1));
await browser.close();
