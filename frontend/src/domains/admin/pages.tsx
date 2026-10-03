import { useState } from 'react';
import { Alert, App, Button, Card, DatePicker, Descriptions, Form, Input, InputNumber, Modal, Select, Switch, Table, Tabs, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useAddStationAlias, useAdminAction, useAdminQuery, useToggleChannel, useUpdateAdminUser, useUpdateStation } from './hooks';
import { dateTime } from '../../shared/api';
import type { Page, Row, User } from '../../shared/api';
import { Heading, QueryState } from '../../shared/components';
import { useWorkbench } from '../../shared/context';

export function StationEditor() {
  const query = useAdminQuery<Page>('/stations');
  const cities = useAdminQuery<Page>('/cities');
  const updateStation = useUpdateStation();
  const addAlias = useAddStationAlias();
  const [selected, setSelected] = useState<Row | null>(null);
  const [alias, setAlias] = useState(false);
  const [form] = Form.useForm();
  const { message } = App.useApp();
  return <><Table rowKey="id" scroll={{ x: 700 }} dataSource={query.data?.items} columns={[
    { title: '站点', dataIndex: 'name' }, { title: '编码', dataIndex: 'code' },
    { title: '坐标', render: (_, r) => `${r.longitude ?? '—'}, ${r.latitude ?? '—'}` },
    { title: '状态', dataIndex: 'active', render: v => v ? '启用' : '停用' },
    { title: '维护', render: (_, r) => <><Button type="link" onClick={() => { setAlias(false); setSelected(r); form.setFieldsValue(r); }}>编辑资料</Button><Button type="link" onClick={() => { setAlias(true); setSelected(r); form.resetFields(); }}>添加有效期别名</Button></> },
  ]} /><Modal title={alias ? '添加站点别名' : '编辑站点资料'} open={!!selected} onCancel={() => setSelected(null)} onOk={() => form.submit()}><Form form={form} layout="vertical" onFinish={async values => {
    try {
      const body = alias ? { ...values, valid_from: values.valid_from.format('YYYY-MM-DD'), valid_to: values.valid_to?.format('YYYY-MM-DD') || null } : values;
      await (alias ? addAlias : updateStation).mutateAsync({ id: selected!.id, values: body });
      setSelected(null); query.refetch(); message.success('站点目录已更新');
    } catch (e) { message.error((e as Error).message); }
  }}>{alias ? <><Form.Item name="external_name" label="来源文件中的名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="valid_from" label="适用起始日期" rules={[{ required: true }]}><DatePicker /></Form.Item><Form.Item name="valid_to" label="适用截至日期"><DatePicker /></Form.Item></> : <><Form.Item name="city_id" label="城市" rules={[{ required: true }]}><Select options={cities.data?.items.map(c => ({ value: c.id, label: c.name }))} /></Form.Item>{[['name', '站点名称'], ['code', '站点编码']].map(([key, title]) => <Form.Item key={key} name={key} label={title} rules={[{ required: true }]}><Input /></Form.Item>)}<Form.Item name="latitude" label="纬度"><InputNumber min={-90} max={90} /></Form.Item><Form.Item name="longitude" label="经度"><InputNumber min={-180} max={180} /></Form.Item><Form.Item name="active" label="启用" valuePropName="checked"><Switch /></Form.Item></>}</Form></Modal></>;
}

export function StandardComposer() {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const create = useAdminAction('/admin/standards');
  const pollutant = Form.useWatch('pollutant', form) || 'PM2.5';
  return <><Button onClick={() => { form.resetFields(); setOpen(true); }}>新增标准版本</Button><Modal title="新增环境质量标准版本" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending}><Form form={form} layout="vertical" initialValues={{ pollutant: 'PM2.5', grade: '二级', region: '全国', min_points: 20 }} onFinish={async values => {
    await create.mutateAsync({ ...values, unit: pollutant === 'CO' ? 'mg/m³' : 'μg/m³', basis: pollutant === 'O3' ? 'daily_max_8h' : 'daily_mean', effective_from: values.effective_from.format('YYYY-MM-DD'), effective_to: values.effective_to?.format('YYYY-MM-DD') || null }); setOpen(false);
  }}><p>历史评价保留原标准快照。新版本有效期不得与同地区、等级、指标的启用版本重叠。</p><Form.Item name="code" label="标准编号与阶段" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="pollutant" label="污染物"><Select onChange={v => form.setFieldValue('min_points', v === 'O3' ? 14 : 20)} options={['PM2.5','PM10','SO2','NO2','O3','CO'].map(value => ({ value }))} /></Form.Item><Form.Item name="grade" label="等级"><Select options={['一级','二级'].map(value => ({ value }))} /></Form.Item><Form.Item name="region" label="适用地区" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="limit_value" label={`限值（${pollutant === 'CO' ? 'mg/m³' : 'μg/m³'}）`} rules={[{ required: true }]}><InputNumber min={0.001} /></Form.Item><Form.Item name="min_points" label="最少有效小时或有效8小时窗口"><InputNumber min={1} max={24} /></Form.Item><Form.Item name="effective_from" label="生效日" rules={[{ required: true }]}><DatePicker /></Form.Item><Form.Item name="effective_to" label="截至日"><DatePicker /></Form.Item><Form.Item name="source_url" label="官方原文地址" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item><Form.Item name="article" label="条款与统计依据" rules={[{ required: true }]}><Input.TextArea /></Form.Item></Form></Modal></>;
}

export function ChannelComposer() {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const kind = Form.useWatch('kind', form) || 'webhook';
  const create = useAdminAction('/admin/channels');
  return <><Button onClick={() => { form.resetFields(); setOpen(true); }}>添加通知通道</Button><Modal title="添加通知通道" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending}><Form form={form} layout="vertical" initialValues={{ kind: 'webhook', enabled: false }} onFinish={async values => { const { name, kind, enabled, credential_ref, ...config } = values; await create.mutateAsync({ name, kind, enabled, credential_ref: credential_ref || null, config }); setOpen(false); }}><Form.Item name="name" label="通道名称" rules={[{ required: true, min: 2 }]}><Input /></Form.Item><Form.Item name="kind" label="类型"><Select options={[{ label: 'Webhook', value: 'webhook' }, { label: '邮件', value: 'email' }]} /></Form.Item>{(kind === 'webhook' ? [['url', 'HTTPS 接收地址']] : [['host', 'SMTP 主机'], ['sender', '发件邮箱'], ['recipient', '收件邮箱']]).map(([key, label]) => <Form.Item key={key} name={key} label={label} rules={[{ required: true }]} preserve={false}><Input /></Form.Item>)}{kind === 'email' && <><Form.Item name="port" label="SMTP 端口" initialValue={587} preserve={false}><InputNumber min={1} max={65535} /></Form.Item><Form.Item name="username" label="SMTP 用户名" preserve={false}><Input /></Form.Item></>}<Form.Item name="credential_ref" label="凭据环境变量名（由部署管理员配置）" rules={[{ pattern: /^ESP_NOTIFY_[A-Z0-9_]+$/, message: '使用 ESP_NOTIFY_ 开头的变量名' }]}><Input placeholder="ESP_NOTIFY_MAIL_PASSWORD" /></Form.Item><Form.Item name="enabled" label="启用后开始发送通知" valuePropName="checked"><Switch /></Form.Item></Form></Modal></>;
}

export function ReferenceEndEditor({ item, kind }: { item: Row; kind: 'laws' | 'standards' }) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const save = useAdminAction(`/admin/${kind}/${item.id}/end`, 'PATCH');
  return <><Button type="link" onClick={() => { form.resetFields(); setOpen(true); }}>维护截至日</Button><Modal title="维护依据有效期" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={save.isPending}><p>{item.title || `${item.code} · ${item.pollutant}`}。已有核查和评价中的历史快照会保留。</p><Form form={form} layout="vertical" onFinish={async values => { await save.mutateAsync({ effective_to: values.effective_to.format('YYYY-MM-DD'), reason: values.reason }); setOpen(false); }}><Form.Item name="effective_to" label="截至日期" rules={[{ required: true }]}><DatePicker /></Form.Item><Form.Item name="reason" label="修订依据与替代说明" rules={[{ required: true, min: 5 }]}><Input.TextArea rows={4} /></Form.Item></Form></Modal></>;
}


export function Administration() {
  const { params, setFilter } = useWorkbench();
  const tab = params.get('tab') || 'users';
  return <><Heading title="系统管理" eyebrow="PLATFORM ADMINISTRATION" description="管理账号、参考依据、站点目录与采集运行，所有关键变更保留审计记录。" /><Tabs activeKey={tab} onChange={v => setFilter({ tab: v })} items={[
    { key: 'users', label: '用户与权限', children: <Users /> }, { key: 'sources', label: '数据源与站点', children: <Sources /> },
    { key: 'standards', label: '标准法规', children: <References /> }, { key: 'channels', label: '通知通道', children: <Channels /> },
    { key: 'audit', label: '操作审计', children: <Audits /> },
  ]} /></>;
}

function Users() {
  const query = useAdminQuery<Page<User>>('/admin/users');
  const create = useAdminAction('/admin/users');
  const updateUser = useUpdateAdminUser();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const roles = ['管理员', '监管主管', '执法人员', '研究者'];
  return <Card title="账号目录" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setOpen(true); }}>新建账号</Button>}><QueryState query={query}><Table<Row> rowKey="id" dataSource={query.data?.items} scroll={{ x: 760 }} columns={[{ title: '姓名', dataIndex: 'display_name' }, { title: '登录名', dataIndex: 'username' }, { title: '角色', dataIndex: 'role', render: (v, r) => <Select value={v} options={roles.map(role => ({ label: role, value: role }))} style={{ width: 140 }} onChange={async role => { try { await updateUser.mutateAsync({ id: r.id, role, active: r.active }); query.refetch(); } catch (e) { message.error((e as Error).message); } }} /> }, { title: '账号启用', dataIndex: 'active', render: (v, r) => <Switch checked={v} onChange={async active => { try { await updateUser.mutateAsync({ id: r.id, role: r.role, active }); query.refetch(); } catch (e) { message.error((e as Error).message); } }} /> }, { title: '首次改密', dataIndex: 'must_change_password', render: v => v ? '待完成' : '已完成' }]} /></QueryState><Modal title="新建账号" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending}><Form form={form} layout="vertical" onFinish={async values => { await create.mutateAsync(values); setOpen(false); }}>{[['username', '登录名'], ['display_name', '姓名']].map(([key, label]) => <Form.Item key={key} name={key} label={label} rules={[{ required: true, min: key === 'username' ? 3 : 1 }]}><Input /></Form.Item>)}<Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={roles.map(role => ({ label: role, value: role }))} /></Form.Item><Form.Item name="password" label="初始密码（首次登录必须修改）" rules={[{ required: true, min: 12 }]}><Input.Password autoComplete="new-password" /></Form.Item></Form></Modal></Card>;
}

function Sources() {
  const query = useAdminQuery('/admin/sources');
  const stations = useAdminQuery<Page>('/stations');
  return <><Card title="Quotsoft 北京日文件" className="mb16"><QueryState query={query}><Descriptions column={2} items={[{ label: '更新频率', children: query.data?.schedule }, { label: '持续业务使用许可', children: query.data?.license_confirmed ? <Tag color="success">已确认</Tag> : <Tag color="warning">上线前待确认</Tag> }, { label: '数据来源', children: <a href="https://quotsoft.net/air/" target="_blank" rel="noreferrer">Quotsoft 来源说明 ↗</a> }, { label: '数据规则', children: query.data?.observation_rule }]} /><Table rowKey="id" size="small" dataSource={query.data?.files.items} scroll={{ x: 800 }} columns={[{ title: '观测日期', dataIndex: 'local_date' }, { title: '文件类型', dataIndex: 'kind' }, { title: '来源', dataIndex: 'origin' }, { title: '入库时间', dataIndex: 'created_at', render: dateTime }, { title: '有效修订', dataIndex: 'is_current', render: v => v ? '当前' : '历史保留' }, { title: '观测数量', dataIndex: 'row_count' }]} /></QueryState></Card><Card title="站点目录"><StationEditor /><details><summary>原始目录概览</summary><QueryState query={stations}><Table rowKey="id" dataSource={stations.data?.items} columns={[{ title: '站点名称', dataIndex: 'name' }, { title: '站点编码', dataIndex: 'code' }, { title: '纬度', dataIndex: 'latitude' }, { title: '经度', dataIndex: 'longitude' }, { title: '启用状态', dataIndex: 'active', render: v => v ? '启用' : '停用' }]} /></QueryState></details></Card></>;
}

function References() {
  const standards = useAdminQuery<Page>('/standards');
  const laws = useAdminQuery<Page>('/laws');
  const create = useAdminAction('/admin/laws');
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  return <><Card title="环境质量评价标准" className="mb16" extra={<StandardComposer />}><QueryState query={standards}><Table rowKey="id" dataSource={standards.data?.items} scroll={{ x: 1000 }} columns={[{ title: '标准版本', dataIndex: 'code' }, { title: '污染物', dataIndex: 'pollutant' }, { title: '等级', dataIndex: 'grade' }, { title: '口径', dataIndex: 'basis', render: v => v === 'daily_mean' ? '日均值' : '日最大8小时' }, { title: '限值', render: (_, r) => `${r.limit_value} ${r.unit}` }, { title: '生效日', dataIndex: 'effective_from' }, { title: '截至日', dataIndex: 'effective_to', render: v => v || '持续有效' }, { title: '有效期维护', render: (_, r) => <ReferenceEndEditor item={r} kind="standards" /> }, { title: '原文', render: (_, r) => <a href={r.source_url} target="_blank" rel="noreferrer">查看 ↗</a> }]} /></QueryState></Card><Card title="法规与适用依据" extra={<Button icon={<PlusOutlined />} onClick={() => setOpen(true)}>添加法规版本</Button>}><QueryState query={laws}><Table rowKey="id" dataSource={laws.data?.items} columns={[{ title: '名称', dataIndex: 'title' }, { title: '适用地区', dataIndex: 'region' }, { title: '生效日', dataIndex: 'effective_from' }, { title: '截至日', dataIndex: 'effective_to', render: v => v || '持续有效' }, { title: '有效期维护', render: (_, r) => <ReferenceEndEditor item={r} kind="laws" /> }, { title: '原文', render: (_, r) => <a href={r.source_url} target="_blank" rel="noreferrer">查看 ↗</a> }]} expandable={{ expandedRowRender: r => r.summary }} /></QueryState></Card><Modal title="新增法规版本" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()}><Form form={form} layout="vertical" onFinish={async values => { await create.mutateAsync({ ...values, effective_from: values.effective_from.format('YYYY-MM-DD'), effective_to: values.effective_to?.format('YYYY-MM-DD') || null }); setOpen(false); }}>{[['title', '法规名称与版本'], ['region', '适用地区'], ['source_url', '官方原文地址']].map(([key, title]) => <Form.Item key={key} name={key} label={title} rules={[{ required: true }]}><Input /></Form.Item>)}<Form.Item name="effective_from" label="生效日期" rules={[{ required: true }]}><DatePicker /></Form.Item><Form.Item name="effective_to" label="失效日期"><DatePicker /></Form.Item><Form.Item name="summary" label="适用说明与替代关系" rules={[{ required: true, min: 5 }]}><Input.TextArea rows={4} /></Form.Item></Form></Modal></>;
}

function Channels() {
  const query = useAdminQuery('/admin/channels');
  const toggleChannel = useToggleChannel();
  return <Card title="通知通道与发送记录" extra={<ChannelComposer />}><Alert type="info" showIcon message="站内通知默认启用。邮件与 Webhook 仅向管理员显式配置并启用的通道发送。" className="mb16" /><QueryState query={query}><Table<Row> rowKey="id" dataSource={query.data?.items} columns={[{ title: '通道名称', dataIndex: 'name' }, { title: '类型', dataIndex: 'kind' }, { title: '启用', dataIndex: 'enabled', render: (v, r) => <Switch checked={v} onChange={async enabled => { await toggleChannel.mutateAsync({ id: r.id, enabled }); query.refetch(); }} /> }]} /><h3>发送历史</h3><Table rowKey="id" dataSource={query.data?.deliveries.items} columns={[{ title: '通知编号', dataIndex: 'notification_id' }, { title: '状态', dataIndex: 'status' }, { title: '尝试次数', dataIndex: 'attempts' }, { title: '失败原因', dataIndex: 'error' }]} /></QueryState></Card>;
}

function Audits() {
  const { params, setFilter } = useWorkbench();
  const query = useAdminQuery<Page>(`/admin/audits?page_number=${params.get('page_number') || 1}`);
  return <Card title="不可变操作审计"><QueryState query={query}><Table<Row> rowKey="id" dataSource={query.data?.items} scroll={{ x: 950 }} pagination={{ pageSize: 50, total: query.data?.total, current: Number(params.get('page_number') || 1), showSizeChanger: false, onChange: p => setFilter({ page_number: String(p) }) }} columns={[{ title: '时间', dataIndex: 'created_at', render: dateTime }, { title: '操作', dataIndex: 'action' }, { title: '对象类型', dataIndex: 'object_type' }, { title: '对象编号', dataIndex: 'object_id', ellipsis: true }, { title: '请求编号', dataIndex: 'request_id', ellipsis: true }]} expandable={{ expandedRowRender: r => <pre className="json-detail">{JSON.stringify(r.detail, null, 2)}</pre> }} /></QueryState></Card>;
}
