import { test, expect, type Page } from '@playwright/test';

async function login(page: Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('账号', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill('Acceptance-only-2026!');
  await page.getByRole('button', { name: '进入工作台' }).click();
  await expect(page.getByRole('heading', { name: '环境监管工作台' })).toBeVisible();
}

async function choose(page: Page, label: string, name: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.locator('.ant-select-dropdown:visible').getByText(name, { exact: true }).click();
}

async function dateField(page: Page, label: string, value: string) {
  await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByLabel(label, { exact: true }).press('Tab');
}

async function confirm(page: Page, title: string) {
  await page.getByRole('dialog', { name: title, exact: true }).getByRole('button', { name: '确 定' }).click();
  await expect(page.getByRole('dialog', { name: title, exact: true })).toBeHidden();
}

async function transition(page: Page, name: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await page.getByLabel('操作说明 / 审核结论').fill('自动化隔离验收：根据现场记录推进本次测试流程。');
  await confirm(page, name);
}

test('表格导入、主管分派、证据版本、整改复查与审核归档', async ({ page, browser }, info) => {
  test.setTimeout(150000);
  const unique = `${info.project.name}-${Date.now()}`;
  const company = `验收隔离企业-${unique}`;
  const title = `闭环验收-${unique}`;
  await login(page, 'supervisor');
  await page.goto('/enterprises');
  const csv = `企业名称,统一社会信用代码,行业,地址,联系人\n${company},TEST0${Date.now()},测试行业,测试地址,测试联系人\n`;
  await page.locator('input[type=file]').setInputFiles({ name: 'enterprise-acceptance.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await expect(page.getByText('任务进度', { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog').getByText('已完成', { exact: true })).toBeVisible({ timeout: 45000 });
  await page.getByRole('dialog').getByRole('button').first().click();
  await page.reload();
  await expect(page.getByRole('link', { name: company, exact: true })).toBeVisible();
  await page.goto('/leads');
  await page.getByRole('button', { name: '新建线索' }).click();
  await page.getByLabel('线索标题').fill(title);
  await page.getByLabel('事实与待核实事项').fill('仅用于隔离验收：核查企业维护记录，不代表实际违法结论。');
  await confirm(page, '新建待研判线索');
  const row = page.getByRole('row').filter({ hasText: title });
  await row.getByRole('button', { name: '认领', exact: true }).click();
  await expect(row).toContainText('核查主管');
  await row.getByRole('button', { name: '分派核查' }).click();
  await choose(page, '负责人', '现场核查员 · 执法人员');
  await choose(page, '关联企业（经确认后填写）', company);
  await dateField(page, '核查期限', '2026-12-30');
  await page.getByLabel('分派说明').fill('请核对现场事实与维护记录，按流程提交审核。');
  await confirm(page, '分派核查任务');
  const officerContext = await browser.newContext({ viewport: info.project.use.viewport });
  const officer = await officerContext.newPage();
  try {
    // A separate browser context proves role isolation without swapping a session cookie.
    const origin = new URL(page.url()).origin;
    await officer.goto(`${origin}/login`);
    await officer.getByLabel('账号', { exact: true }).fill('officer');
    await officer.getByLabel('密码', { exact: true }).fill('Acceptance-only-2026!');
    await officer.getByRole('button', { name: '进入工作台' }).click();
    await expect(officer.getByRole('heading', { name: '环境监管工作台' })).toBeVisible();
    await officer.goto(`${origin}/inspections`);
    await officer.getByRole('link', { name: new RegExp(title) }).click();
    const taskUrl = officer.url();
    await transition(officer, '开始现场核查');
    await officer.getByLabel('核查事实', { exact: true }).fill('验收现场事实：维护记录存在缺项，已记录设备编号并保留原始附件。');
    await officer.getByRole('button', { name: '保存核查记录' }).click();
    await expect(officer.getByText('核查记录已保存', { exact: true })).toBeVisible();
    await officer.locator('input[type=file]').first().setInputFiles({ name: 'evidence-v1.txt', mimeType: 'text/plain', buffer: Buffer.from('Original inspection evidence v1') });
    await expect(officer.getByText('evidence-v1.txt', { exact: true })).toBeVisible();
    await officer.locator('.attachment-row').filter({ hasText: 'evidence-v1.txt' }).locator('input[type=file]').setInputFiles({ name: 'evidence-v2.txt', mimeType: 'text/plain', buffer: Buffer.from('Additional inspection evidence v2') });
    await expect(officer.getByText('evidence-v2.txt', { exact: true })).toBeVisible();
    await expect(officer.getByText('evidence-v1.txt', { exact: true })).toBeVisible();
    await officer.getByRole('button', { name: '添加整改事项' }).click();
    await officer.getByLabel('整改要求', { exact: true }).fill('补齐维护记录，提供校准文件并接受现场复查。');
    await dateField(officer, '整改期限', '2026-12-20');
    await confirm(officer, '添加整改要求');
    await transition(officer, '进入整改跟踪');
    await officer.getByRole('button', { name: '填写整改反馈' }).click();
    await officer.getByLabel('整改完成情况').fill('维护记录及校准文件已补齐，申请复查。');
    await confirm(officer, '记录整改反馈');
    await transition(officer, '提交整改复查');
    await officer.getByRole('button', { name: '填写复查结论' }).click();
    await officer.getByLabel('复查事实与结论').fill('已核对资料和现场设备，测试整改要求完成。');
    await officer.getByLabel('已核实该项整改完成').check();
    await confirm(officer, '记录复查结论');
    await transition(officer, '提交主管审核');
    await expect(officer.getByRole('button', { name: '审核通过并归档' })).toHaveCount(0);
    await page.goto(taskUrl);
    await transition(page, '审核通过并归档');
    await expect(page.getByRole('button', { name: '重新开启核查' })).toBeVisible();
    await expect(page.getByRole('button', { name: '上传证据' })).toHaveCount(0);
    await page.screenshot({ path: `test-results/closure-${info.project.name}.png`, fullPage: true });
  } finally { await officerContext.close(); }
});
