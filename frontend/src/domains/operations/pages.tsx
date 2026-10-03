import { useState } from 'react';
import { Alert, App, Button, Card, DatePicker, Descriptions, Form, Input, Modal, Progress, Select, Space, Switch, Table,  Tag, Upload } from 'antd';
import { DownloadOutlined, ExperimentOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { dateTime, number, queryString } from '../../shared/api';
import type { Page, Row } from '../../shared/api';
import { Heading, labels, QueryState, Status } from '../../shared/components';
import { useWorkbench } from '../../shared/context';
import { useJobs, useCreateJob, useRetryJob } from '../jobs/hooks';
import { useImportJob, useModelActivate, useModelRollback, useOperationsAction, useOperationsQuery } from './hooks';

export function Reports() {
  const { start, end, city, openJob, user, params, setFilter } = useWorkbench();
  const query = useJobs(`/jobs?${queryString({ status: params.get('status'), page_number: params.get('page_number') || 1 })}`);
  const create = useCreateJob();
  const importJob = useImportJob();
  const retry = useRetryJob();
  const { message } = App.useApp();
  const [report, setReport] = useState('observations');
  const [format, setFormat] = useState('csv');
  const [importKind, setImportKind] = useState('all');
  const statuses = ['queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled'];
  return <>
    <Heading title="报告与下载" eyebrow="REPORTS & OPERATIONS" description="长时间操作在后台执行，任务进度、失败原因和历史结果都可以追踪。" />
    <div className="two-columns">
      <Card title="生成数据报告"><Form layout="vertical">
        <Form.Item label="报告内容"><Select value={report} onChange={setReport} options={[{ label: '原始环境观测', value: 'observations' }, ...(user.role !== '研究者' ? [{ label: '授权核查任务汇总', value: 'inspections' }] : [])]} /></Form.Item>
        <Form.Item label="文件格式"><Select value={format} onChange={setFormat} options={[{ value: 'csv', label: 'CSV · 数据交换' }, { value: 'xlsx', label: 'Excel · 包含来源说明' }]} /></Form.Item>
        <div className="form-footer"><span className="muted">{start} 至 {end}</span><Button type="primary" icon={<DownloadOutlined />} loading={create.isPending} onClick={async () => { const result = await create.mutateAsync({ kind: 'export', start, end, city_id: city, report, format }); openJob(String(result.job_id)); }}>创建导出任务</Button></div>
      </Form></Card>
      <Card title="数据导入与采集">{['管理员', '监管主管'].includes(user.role) ? <>
        <p className="muted">上传 UTF-8 日文件或企业表格。重复内容会跳过，来源修订保留原文件。</p>
        <Form layout="vertical"><Form.Item label="导入内容"><Select value={importKind} onChange={setImportKind} options={[{ value: 'all', label: '颗粒物日文件（PM2.5、PM10、AQI）' }, { value: 'extra', label: '气态污染物日文件（SO₂、NO₂、O₃、CO）' }, { value: 'enterprises', label: '企业档案表格' }]} /></Form.Item>
          <Upload accept=".csv" showUploadList={false} beforeUpload={async file => { const body = new FormData(); body.append('file', file); body.append('kind', importKind); try { const result = await importJob.mutateAsync(body); openJob(String(result.job_id)); } catch (error) { message.error((error as Error).message); } return false; }}><Button icon={<UploadOutlined />}>选择 CSV 并创建导入任务</Button></Upload>
        </Form>
        {user.role === '管理员' && <div className="section-card"><Button icon={<ReloadOutlined />} loading={create.isPending} onClick={async () => { const result = await create.mutateAsync({ kind: 'collect', start, end }); openJob(String(result.job_id)); }}>补采当前日期范围</Button><p className="card-footnote">自动采集每日 03:30 运行，重查近七天迟到或修订文件。</p></div>}
      </> : <><Alert type="info" showIcon message="研究者可创建环境数据导出，查看本人任务与下载结果。" /><p className="muted">数据导入与数据源维护由管理员或监管主管负责。</p></>}</Card>
    </div>
    <Card title="任务运行记录" className="section-card" extra={<Select aria-label="任务状态筛选" style={{ width: 150 }} value={params.get('status') || ''} onChange={value => setFilter({ status: value })} options={[{ label: '全部状态', value: '' }, ...statuses.map(value => ({ label: labels[value], value }))]} />}>
      <QueryState query={query}><Table<Row> rowKey="id" dataSource={query.data?.items} scroll={{ x: 1000 }} pagination={{ pageSize: 20, total: query.data?.total, current: Number(params.get('page_number') || 1), showSizeChanger: false, onChange: page => setFilter({ page_number: String(page) }) }} columns={[
        { title: '任务类型', dataIndex: 'kind', render: value => labels[value] || value }, { title: '创建时间', dataIndex: 'created_at', render: dateTime }, { title: '状态', dataIndex: 'status', render: value => <Status value={value} /> }, { title: '进度', dataIndex: 'progress', width: 160, render: (value, row) => <Progress percent={value} size="small" status={row.status === 'failed' ? 'exception' : undefined} /> }, { title: '执行次数', dataIndex: 'attempts' },
        { title: '操作', width: 240, render: (_, row) => <Space><Button type="link" onClick={() => openJob(row.id)}>查看详情</Button>{row.download_available && <Button type="link" href={`/api/v2/jobs/${row.id}/download`}>下载</Button>}{['failed', 'partial'].includes(row.status) && <Button type="link" onClick={async () => { try { const next = await retry.mutateAsync({ id: row.id }); openJob(String(next.job_id)); } catch (error) { message.error((error as Error).message); } }}>重试</Button>}</Space> },
      ]} /></QueryState>
    </Card>
  </>;
}
export function Models() {
  const { start, end, user, openJob } = useWorkbench();
  const query = useOperationsQuery<Page & { activations: Row[] }>('/models', true, true);
  const create = useOperationsAction('/jobs');
  const rollback = useModelRollback();
  const activate = useModelActivate();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const task = Form.useWatch('task', form) || 'forecast';
  return <><Heading title="模型中心" eyebrow="MODEL REGISTRY" description="对比可复现的实验结果，验证通过后由管理员发布；保留上一可用版本。" extra={user.role === '管理员' && <Button type="primary" icon={<ExperimentOutlined />} onClick={() => setOpen(true)}>创建训练任务</Button>} /><Alert type="info" showIcon className="mb16" message="训练、验证、测试按时间隔离；归一化仅拟合训练集。候选模型未达到基线时保留实验状态。" /><div className="two-columns">{[['forecast', '浓度预测'], ['imputation', '离线插补']].map(([key, title]) => { const active = query.data?.activations.find(a => a.task === key); const model = query.data?.items.find(m => m.id === active?.model_id); return <Card key={key} title={title} extra={active && user.role === '管理员' && <Button size="small" disabled={!active.previous_id} onClick={async () => { try { await rollback.mutateAsync({ task: key }); query.refetch(); message.success('已恢复上一可用模型'); } catch (e) { message.error((e as Error).message); } }}>回滚版本</Button>}><div className="active-model"><ExperimentOutlined /><div><strong>{model?.algorithm || '尚未激活模型'}</strong><small>{model ? `发布于 ${dateTime(active?.updated_at)}` : '先完成训练、评估与制品重载验证'}</small></div>{model && <Tag color="success">当前使用</Tag>}</div><div className="form-footer"><span className="muted">{start} 至 {end}</span><Button disabled={!active} loading={create.isPending} onClick={async () => { const r = await create.mutateAsync({ kind: key === 'forecast' ? 'forecast' : 'impute', start, end }); openJob(r.job_id); }}>{key === 'forecast' ? '运行24小时预测' : '运行辅助插补'}</Button></div></Card>; })}</div><Card title="实验与版本" className="section-card"><QueryState query={query}><Table<Row> rowKey="id" dataSource={query.data?.items} scroll={{ x: 850 }} columns={[{ title: '算法', dataIndex: 'algorithm', render: v => <strong>{v}</strong> }, { title: '任务', dataIndex: 'task', render: v => v === 'forecast' ? '24小时预测' : '数据插补' }, { title: '验证状态', dataIndex: 'status', render: v => <Status value={v} /> }, { title: '创建时间', dataIndex: 'created_at', render: dateTime }, { title: '数据范围', render: (_, r) => `${r.manifest.snapshot.start} — ${r.manifest.snapshot.end}` }, { title: '操作', render: (_, r) => user.role === '管理员' && <Button type="link" disabled={r.status !== 'validated'} onClick={async () => { try { await activate.mutateAsync({ id: r.id }); query.refetch(); message.success('模型已激活'); } catch (e) { message.error((e as Error).message); } }}>激活此版本</Button> }]} expandable={{ expandedRowRender: r => <><Descriptions size="small" column={2} items={[{ label: '数据快照', children: <code>{r.manifest.snapshot.sha256}</code>, span: 2 }, { label: '随机种子', children: r.manifest.seed }, { label: '窗口隔离', children: r.manifest.validation.no_cross_split_windows ? '已验证' : '待验证' }, { label: '制品重载', children: r.manifest.validation.reload_checked ? '已验证' : '未通过' }, { label: '基线比较', children: r.manifest.validation.baseline_passed ? '通过' : '未通过' }]} />{r.task === 'forecast' ? <Table<Row> size="small" pagination={false} rowKey="pollutant" dataSource={Object.entries(r.metrics).map(([pollutant, value]) => ({ pollutant, ...(value as Row) }))} columns={[{ title: '污染物', dataIndex: 'pollutant' }, { title: '测试 MAE', render: (_, m) => number(m.test.MAE, 3) }, { title: '测试 RMSE', render: (_, m) => number(m.test.RMSE, 3) }, { title: '基线 MAE', render: (_, m) => number(m.baseline.MAE, 3) }, { title: '90%区间实测覆盖率', render: (_, m) => `${number(m.test.coverage_90 * 100)}%` }, { title: '测试样本量', render: (_, m) => m.test.n }]} /> : <pre className="json-detail">{JSON.stringify(r.metrics, null, 2)}</pre>}<details><summary>复现环境与适用条件</summary><pre className="json-detail">{JSON.stringify(r.manifest, null, 2)}</pre></details></> }} /></QueryState></Card><Modal title="创建可复现的训练任务" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending}><p>数据范围：{start} 至 {end}。按时间 70% / 15% / 15% 划分。</p><Form form={form} layout="vertical" initialValues={{ task: 'forecast', algorithm: 'seasonal', seed: 42 }} onFinish={async values => { const r = await create.mutateAsync({ ...values, seed: Number(values.seed), kind: 'train', start, end }); setOpen(false); openJob(r.job_id); }}><Form.Item name="task" label="任务类型"><Select onChange={v => form.setFieldValue('algorithm', v === 'forecast' ? 'seasonal' : 'interpolation')} options={[{ value: 'forecast', label: 'PM2.5 / PM10 24小时预测' }, { value: 'imputation', label: '六项污染物离线插补' }]} /></Form.Item><Form.Item name="algorithm" label="算法"><Select options={(task === 'forecast' ? ['seasonal', 'lightgbm'] : ['interpolation', 'SAITS', 'BRITS']).map(v => ({ value: v, label: ({ seasonal: '季节基线', interpolation: '线性插值基线' } as Row)[v] || v }))} /></Form.Item><Form.Item name="seed" label="随机种子" rules={[{ required: true }]}><Input type="number" /></Form.Item></Form></Modal></>;
}

