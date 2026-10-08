import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { App, Button, Card, Checkbox, DatePicker, Form, Input, Radio, Segmented, Select, Space, Steps, Table, Tabs, Tag, Timeline, Upload } from 'antd';
import { CameraOutlined, CheckOutlined, CloudUploadOutlined, FileImageOutlined, FileTextOutlined, HistoryOutlined, WarningOutlined } from '@ant-design/icons';
import { NOW, aqiAt, stationById, stations, tasks } from '../mock';
import { AqiBadge, DeadlineBar, SectionTitle, StatusTag } from '../ui';

const flow = ['线索创建', '认领', '分派', '现场核查', '整改', '复查', '主管审核', '闭环'];
const stepOf: Record<string, number> = { pending: 0, assigned: 2, inspection: 3, rectification: 4, reinspection: 5, review: 6, closed: 7, returned: 3, overdue: 4 };

export function InspectionList() {
  const navigate = useNavigate();
  const [status, setStatus] = useState('all');
  const rows = tasks.filter(t => status === 'all' || t.status === status);
  return (
    <>
      <div className="p-heading"><div><h1>核查与整改</h1><p>线索认领、现场核查、整改跟踪、复查与主管审核的全流程。</p></div></div>
      <Card>
        <div className="p-table-toolbar">
          <Segmented value={status} onChange={v => setStatus(String(v))} options={[
            { label: `全部 ${tasks.length}`, value: 'all' }, { label: '现场核查', value: 'inspection' }, { label: '整改中', value: 'rectification' },
            { label: '复查', value: 'reinspection' }, { label: '主管审核', value: 'review' }, { label: '已退回', value: 'returned' }, { label: '已超期', value: 'overdue' },
          ]} />
          <Input.Search placeholder="任务编号 / 企业" style={{ width: 240 }} />
        </div>
        <Table rowKey="id" dataSource={rows} onRow={r => ({ onClick: () => navigate(`/inspections/${r.id}`), style: { cursor: 'pointer' } })} columns={[
          { title: '任务编号', dataIndex: 'id', render: v => <code>{v}</code> },
          { title: '事项', render: (_, r) => <><strong>{r.title}</strong><small className="block muted">{r.enterprise}</small></> },
          { title: '状态', dataIndex: 'status', render: v => <StatusTag value={v} /> },
          { title: '负责人', dataIndex: 'owner' },
          { title: '关联站点', render: (_, r) => `${stationById(r.station).name} · ${r.pollutant}` },
          { title: '期限', width: 200, render: (_, r) => <DeadlineBar created={r.created} due={r.due} compact /> },
        ]} />
      </Card>
    </>
  );
}

export function InspectionDetail() {
  const { id } = useParams();
  const { modal, message } = App.useApp();
  const task = tasks.find(t => t.id === id) ?? tasks[0];
  const [savedAt, setSavedAt] = useState(NOW.subtract(6, 'minute'));
  const [version, setVersion] = useState('v3');
  const near = stations.filter(s => Math.hypot(s.lon - stationById(task.station).lon, s.lat - stationById(task.station).lat) < 0.12).slice(0, 4);
  const conflict = () => modal.warning({
    title: '记录已被他人更新',
    content: '王五在 14:02 修改了“现场事实”（版本 7 → 8）。你的修改已保存为本地草稿，请刷新查看最新内容后再提交。',
    okText: '刷新并对比',
  });
  return (
    <div className="p-inspection">
      <div className="p-insp-head">
        <div className="grow">
          <div className="p-insp-meta"><code>{task.id}</code><StatusTag value={task.status} /><span className="muted">创建于 {task.created}</span></div>
          <h1>{task.title} · {task.enterprise}</h1>
          <div className="p-insp-people"><span>负责人 <b>{task.owner}</b></span><span>协作 <b>王五</b></span><span>审核 <b>张三</b></span></div>
        </div>
        <div className="p-insp-due"><small>整改期限 {task.due}</small><DeadlineBar created={task.created} due={task.due} /></div>
      </div>
      <Card className="p-flow"><Steps size="small" current={stepOf[task.status] ?? 0} status={task.status === 'returned' || task.status === 'overdue' ? 'error' : 'process'} items={flow.map(title => ({ title }))} /></Card>

      <div className="p-insp-grid">
        <Card className="p-insp-main">
          <Tabs items={[
            { key: 'facts', label: '现场事实', children: (
              <Form layout="vertical" onValuesChange={() => setSavedAt(NOW)} initialValues={{ found: 'yes', types: ['扬尘'] }}>
                <div className="p-autosave"><CheckOutlined /> 已自动暂存 {savedAt.format('HH:mm')} · 版本 7</div>
                <div className="p-form-2">
                  <Form.Item label="核查时间" required><DatePicker showTime style={{ width: '100%' }} defaultValue={NOW.subtract(1, 'day').hour(10)} /></Form.Item>
                  <Form.Item label="现场人员" required><Select mode="multiple" defaultValue={['李四', '王五']} options={['李四', '王五', '赵六'].map(v => ({ value: v, label: v }))} /></Form.Item>
                </div>
                <Form.Item label="是否发现问题" name="found"><Radio.Group optionType="button" options={[{ label: '发现问题', value: 'yes' }, { label: '未发现问题', value: 'no' }]} /></Form.Item>
                <Form.Item label="问题类型" name="types"><Checkbox.Group options={['扬尘', '露天堆放未苫盖', '废气未收集', '设施未运行', '其他']} /></Form.Item>
                <Form.Item label="现场情况描述" required extra="请客观记录看到的事实，不写推断性结论。">
                  <Input.TextArea rows={5} defaultValue={'堆场东侧约 300 平方米砂石料未苫盖，现场有车辆装卸作业，未见喷淋设施运行。\n企业现场负责人称喷淋泵故障，已报修。'} />
                </Form.Item>
              </Form>) },
            { key: 'evidence', label: <>证据 <Tag bordered={false}>{version}</Tag></>, children: (
              <>
                <div className="p-table-toolbar">
                  <Space><span className="muted">版本</span><Segmented value={version} onChange={v => setVersion(String(v))} options={['v1', 'v2', 'v3']} /><Button size="small" icon={<HistoryOutlined />}>对比 v2 ↔ v3</Button></Space>
                  <Upload showUploadList={false} beforeUpload={() => { message.success('原型：已模拟上传'); return false; }}><Button type="primary" icon={<CameraOutlined />}>拍照 / 上传</Button></Upload>
                </div>
                <div className="p-evidence-grid">
                  {['堆场东侧全景', '未苫盖区域近景', '喷淋设施', '车辆装卸', '企业说明材料', '整改承诺书'].map((n, i) => (
                    <div key={n} className={`p-evidence ${i === 5 && version !== 'v3' ? 'is-missing' : ''} ${i === 2 && version === 'v3' ? 'is-new' : ''}`}>
                      <div className="p-evidence-thumb">{i >= 4 ? <FileTextOutlined /> : <FileImageOutlined />}</div>
                      <strong>{n}</strong><small className="mono">sha256 {(0x9c1e7a * (i + 3)).toString(16).slice(0, 8)}…</small>
                      {i === 2 && version === 'v3' && <Tag color="processing" bordered={false}>本版新增</Tag>}
                    </div>
                  ))}
                </div>
                <p className="p-note muted">证据文件不可变，按内容哈希存储；每次下载都会重新校验权限并留痕。</p>
              </>) },
            { key: 'rect', label: '整改要求', children: (
              <Table size="small" pagination={false} rowKey="n" dataSource={[
                { n: 1, req: '裸露砂石料全部苫盖', due: task.due, st: 'rectification' }, { n: 2, req: '修复并启用喷淋设施，留存运行记录', due: task.due, st: 'rectification' }, { n: 3, req: '装卸作业时段洒水降尘', due: task.due, st: 'closed' },
              ]} columns={[{ title: '#', dataIndex: 'n', width: 40 }, { title: '整改事项', dataIndex: 'req' }, { title: '期限', dataIndex: 'due' }, { title: '状态', dataIndex: 'st', render: v => <StatusTag value={v} /> }]} />) },
            { key: 'law', label: '适用法规', children: (
              <div className="p-law">
                <div className="p-law-item"><Tag bordered={false} color="processing">已选</Tag><div><strong>《北京市大气污染防治条例》第六十八条</strong><p>…物料堆放场所应当采取密闭、围挡、遮盖、喷淋等防尘措施…</p><small className="muted">快照于 {NOW.subtract(1, 'day').format('YYYY-MM-DD HH:mm')} · 适用理由由执法人员填写</small></div></div>
                <Input.TextArea rows={3} placeholder="适用理由（必填）：说明事实与条款的对应关系" />
                <p className="p-note muted">条款需人员逐条选择并说明理由；系统不会根据空气数据自动归责企业。</p>
              </div>) },
            { key: 'log', label: '操作记录', children: (
              <Timeline items={[
                { color: 'gray', children: <>10-03 09:12 · 张三 由超限记录生成线索<small className="block muted">{stationById(task.station).name} {task.pollutant} 1.32×</small></> },
                { color: 'gray', children: '10-03 10:40 · 张三 分派给 李四，协作 王五' },
                { color: 'blue', children: '10-08 10:05 · 李四 提交现场事实（版本 5）' },
                { color: 'blue', children: '10-08 16:22 · 李四 上传证据 v2（5 个文件）' },
                { color: 'orange', children: '10-09 13:46 · 李四 下达整改要求 3 项，期限 ' + task.due },
              ]} />) },
          ]} />
        </Card>

        <aside className="p-stack">
          <Card size="small" title="关联线索与超限记录">
            <div className="p-related"><WarningOutlined /><div><strong>{stationById(task.station).name} · {task.pollutant}</strong><small>{task.created} 日均超限 1.32×</small></div></div>
            <Link to={`/stations/${task.station}`}>查看站点详情</Link>
          </Card>
          <Card size="small" title="企业档案摘要" extra={<Link to="/enterprises">档案</Link>}>
            <dl className="p-dl"><dt>统一社会信用代码</dt><dd className="mono">91110***********7X</dd><dt>行业</dt><dd>建材批发 / 堆场</dd><dt>历史核查</dt><dd>2 次 · 1 次整改闭环</dd></dl>
          </Card>
          <Card size="small" title="周边站点当时空气">
            {near.map(s => <div key={s.id} className="p-near"><span>{s.name}</span><AqiBadge aqi={aqiAt(s.id).aqi} size="sm" /></div>)}
          </Card>
        </aside>
      </div>

      <div className="p-action-bar">
        <span className="muted">未保存的修改离开页面前会提示 · 提交时校验版本，冲突返回 409</span>
        <Space>
          <Button onClick={conflict}>演示：版本冲突</Button>
          <Button onClick={() => { setSavedAt(NOW); message.success('草稿已保存'); }}>保存草稿</Button>
          <Button type="primary" icon={<CloudUploadOutlined />}>提交复查</Button>
        </Space>
      </div>
    </div>
  );
}
