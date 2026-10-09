// Extended capture pass v2 — selectors verified against src domains.
// Run: docker run --rm --network environmental-platform_default -v <repo>:/workspace \
//   -w /workspace/frontend/.proto-check -e BASE=http://manual-web \
//   mcr.microsoft.com/playwright:v1.63.0-noble node manual-more.mjs
import { chromium } from '@playwright/test';

const BASE = process.env.BASE || 'http://host.docker.internal:8090';
const OUT = '/workspace/docs/system-manual/assets';
const INSPECTION = '63e229bc-1e10-49a2-814d-49ed0ef2e7ae';
const STATION = '98859dc0-28d2-4bf2-951e-57b543bf1b52';
const ENTERPRISE = '5af533fa-987c-478d-b8b4-e7613be3a570';
const errors = [];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
page.on('pageerror', e => errors.push(`pageerror ${page.url()}: ${e.message}`));
page.on('console', m => { if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(`console ${page.url()}: ${m.text()}`); });

async function login(username, password) {
  const res = await ctx.request.post(`${BASE}/api/v2/auth/login`, { data: { username, password } });
  if (!res.ok()) throw new Error(`login ${username} failed: ${res.status()} ${await res.text()}`);
}

async function shot(path, name, opts = {}) {
  if (path) await page.goto(BASE + path, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(opts.wait ?? 2200);
  if (opts.act) await opts.act();
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: opts.full ?? true });
  console.log('shot', name);
}
async function clickTab(text) {
  const t = page.locator('.ant-tabs-tab').filter({ hasText: text }).first();
  if (await t.count()) { await t.click(); await page.waitForTimeout(1500); return true; }
  return false;
}
async function clickBtn(text) {
  const b = page.locator('button').filter({ hasText: text }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(1200); return true; }
  return false;
}

await login('docshot', 'DocShot2026manual');

// 监测分析：数据质量 Tab
await shot('/monitoring', 'm20-monitoring-quality', { act: async () => { await clickTab('数据质量'); } });
// 评价：展开行（标准快照）
await shot('/evaluations?status=exceeded', 'm21-evaluations-expanded', { act: async () => {
  const ic = page.locator('.ant-table-row-expand-icon').first();
  if (await ic.count()) { await ic.click(); await page.waitForTimeout(1200); }
} });
// 评价：创建线索弹窗（行内按钮"生成线索"或类似）
await shot('/evaluations?status=exceeded', 'm22-evaluations-lead-modal', { act: async () => {
  await clickBtn('线索') || await clickBtn('生成');
} });
// 线索：新建弹窗
await shot('/leads', 'm23-lead-create', { act: async () => { await clickBtn('新建线索'); } });
// 线索：分派弹窗
await shot(null, 'm24-lead-assign', { act: async () => {
  await page.keyboard.press('Escape'); await page.waitForTimeout(400);
  const b = page.locator('button').filter({ hasText: '分派核查' }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(1400); }
} });
// 线索：驳回弹窗
await shot(null, 'm25-lead-reject', { act: async () => {
  await page.keyboard.press('Escape'); await page.waitForTimeout(400);
  const b = page.locator('button').filter({ hasText: '驳回' }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(1200); }
} });

// 核查详情（李强视角）：整改反馈弹窗 + 流转弹窗
await login('liqiang', 'Officer2026pass');
await shot(`/inspections/${INSPECTION}`, 'm26-insp-full');
await shot(null, 'm27-insp-rectif-modal', { act: async () => {
  const b = page.locator('button').filter({ hasText: '填写整改反馈' }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(1200); }
} });
await shot(null, 'm28-insp-transition-modal', { act: async () => {
  await page.keyboard.press('Escape'); await page.waitForTimeout(400);
  const b = page.locator('header button, .ant-btn').filter({ hasText: '提交整改复查' }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(1200); }
} });

// 管理后台其余分区
await login('docshot', 'DocShot2026manual');
await shot('/admin?tab=standards', 'm29-admin-standards');
await shot('/admin?tab=channels', 'm30-admin-channels');
await shot('/admin?tab=audit', 'm31-admin-audits');
await shot('/admin?tab=users', 'm32-admin-users-modal', { act: async () => { await clickBtn('新建账号'); } });

// 修改密码页
await shot('/change-password', 'm33-change-password');

// 通知抽屉
await shot('/', 'm34-notifications', { act: async () => {
  const bell = page.locator('button[aria-label="查看通知"]').first();
  if (await bell.count()) { await bell.click(); await page.waitForTimeout(1200); }
} });

// 预测：运行任务 → 任务进度抽屉（真实创建一条 forecast 任务）
await shot('/forecasts', 'm35-forecast-job', { act: async () => {
  const b = page.locator('button').filter({ hasText: '运行预测' }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(3500); }
} });

// 报告页：任务详情抽屉
await shot('/reports', 'm36-report-job-drawer', { act: async () => {
  const b = page.locator('button').filter({ hasText: '查看详情' }).first();
  if (await b.count()) { await b.click(); await page.waitForTimeout(1500); }
} });

console.log('errors:', JSON.stringify(errors, null, 1));
await browser.close();
