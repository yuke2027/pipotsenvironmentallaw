import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Avatar, Badge, Button, DatePicker, Dropdown, Input, Layout, Menu, Modal, Segmented, Select, Space, Tag } from 'antd';
import {
  ApartmentOutlined, AuditOutlined, BarChartOutlined, BellOutlined, CloudOutlined, DashboardOutlined, DownloadOutlined,
  ExperimentOutlined, FileSearchOutlined, FundProjectionScreenOutlined, LogoutOutlined, SafetyCertificateOutlined, SearchOutlined,
  SettingOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { NOW, enterprises, stations, tasks } from './mock';
import { Watermark } from './ui';

export type Role = '监管主管' | '执法人员' | '研究者' | '管理员';
const people: Record<Role, { name: string; no: string }> = {
  监管主管: { name: '张三', no: '0012' }, 执法人员: { name: '李四', no: '0187' }, 研究者: { name: '陈七', no: 'R021' }, 管理员: { name: '管理员', no: 'A001' },
};
const Ctx = createContext<{ role: Role; setRole: (r: Role) => void; person: { name: string; no: string } }>(null!);
export const useProto = () => useContext(Ctx);

export function ProtoProvider({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<Role>('监管主管');
  return <Ctx.Provider value={{ role, setRole, person: people[role] }}>{children}</Ctx.Provider>;
}

const regulator = (r: Role) => r !== '研究者';
const nav = (role: Role) => [
  { type: 'group' as const, label: '监测', children: [
    { key: '/', icon: <DashboardOutlined />, label: '工作台' },
    { key: '/monitoring', icon: <BarChartOutlined />, label: '监测分析' },
    { key: '/evaluations', icon: <SafetyCertificateOutlined />, label: '标准评价' },
    { key: '/forecasts', icon: <ThunderboltOutlined />, label: '趋势预测' },
  ] },
  ...(regulator(role) ? [{ type: 'group' as const, label: '监管', children: [
    { key: '/leads', icon: <FileSearchOutlined />, label: '线索中心' },
    { key: '/inspections', icon: <AuditOutlined />, label: <span className="nav-with-badge">核查与整改<Badge count={3} size="small" /></span> },
    { key: '/enterprises', icon: <ApartmentOutlined />, label: '企业档案' },
  ] }] : []),
  { type: 'group' as const, label: '分析', children: [
    { key: '/models', icon: <ExperimentOutlined />, label: '模型中心' },
    { key: '/reports', icon: <DownloadOutlined />, label: '报告与下载' },
    ...(role === '管理员' ? [{ key: '/admin', icon: <SettingOutlined />, label: '系统管理' }] : []),
  ] },
];
const titles: Record<string, string> = {
  '/': '工作台', '/monitoring': '监测分析', '/stations': '站点详情', '/inspections': '核查与整改', '/evaluations': '标准评价',
  '/forecasts': '趋势预测', '/leads': '线索中心', '/enterprises': '企业档案', '/models': '模型中心', '/reports': '报告与下载', '/admin': '系统管理',
};

export function Shell() {
  const { role, setRole, person } = useProto();
  const location = useLocation();
  const navigate = useNavigate();
  const [search, setSearch] = useState(false);
  const [session, setSession] = useState(false);
  const active = location.pathname === '/' ? '/' : '/' + location.pathname.split('/')[1];
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearch(true); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  useEffect(() => { if (!regulator(role) && ['/leads', '/inspections', '/enterprises'].includes(active)) navigate('/'); }, [role]);

  return (
    <Layout className="p-app">
      <Layout.Sider width={224} className="p-sider">
        <div className="p-brand">
          <span className="p-brand-mark"><CloudOutlined /></span>
          <div><strong>蓝穹云眼</strong><small>环境监管工作台</small></div>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[active]} items={nav(role)} onClick={e => navigate(e.key)} />
        <a className="p-screen-entry" href="#/screen" target="_blank" rel="noreferrer"><FundProjectionScreenOutlined /> 打开态势大屏</a>
        <div className="p-sider-foot"><span className="dot live" />北京 · 单组织工作空间</div>
      </Layout.Sider>
      <Layout className="p-workspace">
        <header className="p-topbar">
          <div className="p-topbar-left">
            <span className="p-title">环境监测与执法辅助平台</span>
            <span className="p-divider" />
            <Select variant="borderless" defaultValue="beijing" options={[{ value: 'beijing', label: '北京市' }]} style={{ width: 96 }} />
            <button className="p-search-trigger" onClick={() => setSearch(true)}><SearchOutlined /> 搜索站点、企业、任务编号<kbd>Ctrl K</kbd></button>
          </div>
          <Space size={14}>
            <div className="p-role-switch" title="仅原型使用：切换角色查看不同首页与菜单">
              <span>原型 · 角色视角</span>
              <Segmented size="small" value={role} onChange={v => setRole(v as Role)} options={['监管主管', '执法人员', '研究者', '管理员']} />
            </div>
            <Badge count={3} size="small"><Button type="text" icon={<BellOutlined />} aria-label="通知" /></Badge>
            <Dropdown menu={{
              items: [{ key: 'r', label: `${role} · 工号 ${person.no}`, disabled: true }, { key: 'pwd', label: '修改密码' }, { key: 'sess', label: '演示：会话即将超时' }, { type: 'divider' }, { key: 'out', icon: <LogoutOutlined />, label: '退出登录' }],
              onClick: ({ key }) => key === 'sess' && setSession(true),
            }}>
              <Button type="text" className="p-user"><Avatar size={28} style={{ background: '#087f8c' }}>{person.name[0]}</Avatar>{person.name}</Button>
            </Dropdown>
          </Space>
        </header>
        <div className="p-contextbar">
          <span className="p-crumb">工作空间 <i>/</i> {titles[active] ?? '记录详情'}</span>
          <Space size={8}>
            <span className="p-context-label">观测日期</span>
            <DatePicker.RangePicker defaultValue={[NOW.subtract(6, 'day'), NOW]} allowClear={false} presets={[
              { label: '近 7 天', value: [NOW.subtract(6, 'day'), NOW] }, { label: '近 30 天', value: [NOW.subtract(29, 'day'), NOW] }, { label: '本月', value: [NOW.startOf('month'), NOW] },
            ]} />
          </Space>
        </div>
        <main className="p-main"><Outlet /></main>
        <footer className="p-footer">蓝穹云眼 · 环境监管工作台<span>公开观测数据辅助研判 · 企业关联与适用依据由人员确认 · 原型界面所有数值均为示例</span></footer>
      </Layout>
      <Watermark text={`${person.name} ${person.no} ${NOW.format('YYYY-MM-DD')}`} />
      <SearchPalette open={search} onClose={() => setSearch(false)} />
      <Modal open={session} title="会话即将超时" okText="继续工作" cancelText="退出登录" onOk={() => setSession(false)} onCancel={() => setSession(false)}>
        <p>为保障账号安全，系统将在 <b>4 分 58 秒</b> 后自动退出。未保存的核查内容已自动暂存为草稿。</p>
      </Modal>
    </Layout>
  );
}

function SearchPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('');
  const navigate = useNavigate();
  const results = useMemo(() => {
    const k = q.trim();
    const all = [
      ...stations.map(s => ({ group: '站点', title: s.name, sub: s.district, to: `/stations/${s.id}` })),
      ...tasks.map(t => ({ group: '核查任务', title: `${t.id} ${t.title}`, sub: t.enterprise, to: `/inspections/${t.id}` })),
      ...enterprises.map(e => ({ group: '企业', title: e, sub: '企业档案', to: '/enterprises' })),
    ];
    return (k ? all.filter(r => r.title.includes(k) || r.sub.includes(k)) : all.slice(0, 3).concat(all.slice(35, 38))).slice(0, 9);
  }, [q]);
  return (
    <Modal open={open} onCancel={onClose} footer={null} closable={false} width={560} className="p-palette" destroyOnHidden>
      <Input autoFocus size="large" prefix={<SearchOutlined />} placeholder="输入站点名、企业名或任务编号" value={q} onChange={e => setQ(e.target.value)} variant="borderless" />
      <div className="p-palette-list">
        {results.length ? results.map(r => (
          <button key={r.group + r.title} onClick={() => { navigate(r.to); onClose(); }}>
            <Tag bordered={false}>{r.group}</Tag><strong>{r.title}</strong><small>{r.sub}</small>
          </button>
        )) : <div className="p-palette-empty">没有匹配结果</div>}
      </div>
      <div className="p-palette-foot">↑↓ 选择 · Enter 打开 · Esc 关闭</div>
    </Modal>
  );
}

export function Placeholder() {
  const location = useLocation();
  return (
    <div className="p-placeholder">
      <h2>{titles['/' + location.pathname.split('/')[1]]}</h2>
      <p>本轮原型聚焦工作台、监测分析、站点详情、核查详情与态势大屏。该页面将沿用同一套 Token 与组件，在下一轮原型中补充。</p>
      <Space><Link to="/">返回工作台</Link><Link to="/monitoring">查看监测分析</Link><Link to="/inspections/T-20261008-03">查看核查详情</Link></Space>
    </div>
  );
}
