import { test, expect } from '@playwright/test';

const credentials = { username: 'admin', password: 'Acceptance-only-2026!' };

test('登录、真实监测筛选、导出任务与响应布局', async ({ page }, info) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: '登录工作台' })).toBeVisible();
  await page.getByLabel('账号', { exact: true }).fill(credentials.username);
  await page.getByLabel('密码', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: '进入工作台' }).click();
  await expect(page.getByRole('heading', { name: '环境监管工作台' })).toBeVisible();
  await expect(page.getByText('Quotsoft 公开来源')).toBeVisible();
  await expect(page.locator('.metric-value').first()).not.toContainText('—');
  await page.screenshot({ path: `test-results/dashboard-${info.project.name}.png`, fullPage: true });
  await page.getByRole('link', { name: '进入监测分析' }).click();
  await expect(page.getByRole('heading', { name: '监测分析' })).toBeVisible();
  await expect(page.getByRole('table').first()).toBeVisible();
  await page.getByRole('combobox', { name: '对比站点' }).click();
  const option = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
  await option.click();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL(/station_ids=/);
  const saved = page.url();
  await page.reload();
  await expect(page).toHaveURL(saved);
  await expect(page.getByRole('heading', { name: '监测分析' })).toBeVisible();
  await page.getByRole('button', { name: '导出当前查询' }).click();
  await expect(page.getByText('任务进度', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '下载结果' })).toBeVisible({ timeout: 45000 });
  await page.getByRole('dialog').getByRole('button').first().click();
  await page.screenshot({ path: `test-results/monitoring-${info.project.name}.png`, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  expect(overflow).toBeFalsy();
  expect(errors).toEqual([]);
});

test('研究者不能进入证据业务', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('账号', { exact: true }).fill('researcher');
  await page.getByLabel('密码', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: '进入工作台' }).click();
  await expect(page.getByRole('heading', { name: '环境监管工作台' })).toBeVisible();
  await expect(page.getByRole('link', { name: '企业档案', exact: true })).toHaveCount(0);
  await page.goto('/enterprises');
  await expect(page.getByText('没有访问权限', { exact: true })).toBeVisible();
});

test('核查事实保存与未保存离开提醒', async ({ page }, info) => {
  const facts = `现场核查测试：设备标识清楚，资料已逐一核对。${info.project.name}-${Date.now()}`;
  await page.goto('/login');
  await page.getByLabel('账号', { exact: true }).fill('officer');
  await page.getByLabel('密码', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: '进入工作台' }).click();
  await expect(page.getByRole('heading', { name: '环境监管工作台' })).toBeVisible();
  // Use the full task list so unrelated acceptance runs cannot push the seed
  // inspection out of the dashboard's compact four-item preview.
  await page.goto('/inspections');
  await page.getByRole('link', { name: /验收测试 · 观测异常现场核查/ }).click();
  await expect(page.getByText('现场核查记录', { exact: true })).toBeVisible();
  await page.getByLabel('核查事实', { exact: true }).fill(facts);
  await page.getByRole('link', { name: '返回任务列表' }).click();
  await expect(page.getByRole('dialog', { name: '核查记录尚未保存' })).toBeVisible();
  await page.getByRole('button', { name: '继续编辑' }).click();
  await page.getByRole('button', { name: '保存核查记录' }).click();
  await expect(page.getByText('核查记录已保存', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('核查事实', { exact: true })).toHaveValue(facts);
  await page.screenshot({ path: `test-results/inspection-${info.project.name}.png`, fullPage: true });
});
