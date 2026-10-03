import { useState } from 'react';
import { Link, Navigate, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { App, Avatar, Badge, Button, DatePicker, Drawer, Dropdown, Empty, Layout, Menu, Progress, Select, Space, Tag } from 'antd';
import { ApartmentOutlined, AuditOutlined, BarChartOutlined, BellOutlined, CloudOutlined, DashboardOutlined, DatabaseOutlined, DownloadOutlined, ExperimentOutlined, FileSearchOutlined, LogoutOutlined, MenuOutlined, SafetyCertificateOutlined, SettingOutlined, ThunderboltOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { dateTime } from './api';
import { WorkbenchContext } from './context';
import { labels, QueryState, Status } from './components';
import { useQueryClient } from '@tanstack/react-query';
import {
  useCancelShellJob,
  useCurrentUser,
  useLogout,
  useMarkNotificationRead,
  useShellCities,
  useShellDashboard,
  useShellJob,
  useShellNotifications,
} from './hooks';

const navigation = [
  { key: '/', label: '工作台', icon: <DashboardOutlined /> },
  { key: '/monitoring', label: '监测分析', icon: <BarChartOutlined /> },
  { key: '/evaluations', label: '标准评价', icon: <SafetyCertificateOutlined /> },
  { key: '/forecasts', label: '趋势预测', icon: <ThunderboltOutlined /> },
  { key: '/leads', label: '线索中心', icon: <FileSearchOutlined />, regulator: true },
  { key: '/inspections', label: '核查与整改', icon: <AuditOutlined />, regulator: true },
  { key: '/enterprises', label: '企业档案', icon: <ApartmentOutlined />, regulator: true },
  { key: '/models', label: '模型中心', icon: <ExperimentOutlined /> },
  { key: '/reports', label: '报告与下载', icon: <DownloadOutlined /> },
  { key: '/admin', label: '系统管理', icon: <SettingOutlined />, admin: true },
];

export function Shell() {
  const me = useCurrentUser();
  const enabled = !!me.data && !me.data.must_change_password;
  const base = useShellDashboard(enabled);
  const cities = useShellCities(enabled);
  const notifications = useShellNotifications(enabled);
  const logout = useLogout();
  const markNotificationRead = useMarkNotificationRead();
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const { message } = App.useApp();
  const [menu, showMenu] = useState(false);
  const [notice, showNotice] = useState(false);
  const [jobId, setJobId] = useState('');
  const start = params.get('start') || dayjs(base.data?.latest_date || undefined).subtract(6, 'day').format('YYYY-MM-DD');
  const end = params.get('end') || base.data?.latest_date || dayjs().subtract(1, 'day').format('YYYY-MM-DD');
  const city = params.get('city_id') || cities.data?.items[0]?.id || '';
  const setFilter = (values: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(values)) { if (value) next.set(key, value); else next.delete(key); }
    if (!('page_number' in values)) next.delete('page_number');
    setParams(next);
  };
  const link = (path: string) => { const q = new URLSearchParams({ start, end }); if (city) q.set('city_id', city); return `${path}${path.includes('?') ? '&' : '?'}${q}`; };
  if (me.error?.status === 401) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (me.data?.must_change_password) return <Navigate to="/change-password" replace />;
  if (!me.data) return <div className="center-state"><QueryState query={me}><span /></QueryState></div>;
  const user = me.data;
  const items = navigation.filter(n => (!n.regulator || user.role !== '研究者') && (!n.admin || user.role === '管理员'));
  const active = location.pathname === '/' ? '/' : '/' + location.pathname.split('/')[1];
  const nav = <><div className="brand"><span className="brand-symbol"><CloudOutlined /></span><div><strong>清境</strong><small>环境监管工作台</small></div><span className="brand-version">2.0</span></div><div className="nav-caption">监测与监管</div><Menu theme="dark" mode="inline" selectedKeys={[active]} items={items.map(n => ({ ...n, label: <Link to={link(n.key)} onClick={() => showMenu(false)}>{n.label}</Link> }))} /><div className="sidebar-bottom"><span className="live-dot" /><div>北京 · 单组织工作空间<small>观测有据，核查有序</small></div></div></>;
  return <WorkbenchContext.Provider value={{ user, start, end, city, params, setFilter, link, openJob: setJobId }}><Layout className="app-layout">
    <Layout.Sider width={226} className="desktop-sidebar">{nav}</Layout.Sider>
    <Drawer placement="left" open={menu} onClose={() => showMenu(false)} width={250} styles={{ body: { padding: 0, background: '#102b37' } }}>{nav}</Drawer>
    <Layout className="workspace"><header className="topbar"><div className="topbar-context"><Button className="mobile-menu" type="text" icon={<MenuOutlined />} aria-label="打开导航" onClick={() => showMenu(true)} /><span className="workspace-name">环境监测与执法辅助平台</span><span className="topbar-divider" /><Select aria-label="城市" value={city || undefined} options={cities.data?.items.map(c => ({ label: c.name, value: c.id }))} onChange={v => setFilter({ city_id: v })} variant="borderless" style={{ width: 100 }} /></div><Space size={16}><Tag className="source-tag"><span className="live-dot" /> 每日更新</Tag><Badge count={notifications.data?.items.filter(n => !n.read_at).length || 0} size="small"><Button type="text" icon={<BellOutlined />} aria-label="查看通知" onClick={() => showNotice(true)} /></Badge><Dropdown menu={{ items: [{ key: 'role', label: user.role, disabled: true }, { key: 'password', label: '修改密码' }, { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' }], onClick: async ({ key }) => { if (key === 'password') navigate('/change-password'); if (key === 'logout') { await logout.mutateAsync({}); client.clear(); navigate('/login'); } } }}><Button type="text" className="user-button"><Avatar size={28}>{user.display_name[0]}</Avatar><span>{user.display_name}</span></Button></Dropdown></Space></header>
    <div className="contextbar"><span>工作空间 <span className="crumb-slash">/</span> {navigation.find(n => n.key === active)?.label || '记录详情'}</span><Space><span className="context-label">观测日期</span><DatePicker.RangePicker value={[dayjs(start), dayjs(end)]} allowClear={false} onChange={v => v && setFilter({ start: v[0]?.format('YYYY-MM-DD'), end: v[1]?.format('YYYY-MM-DD') })} /></Space></div>
    <main className="main-content" id="main-content"><Outlet /></main><footer className="footer">清境 · 环境监管工作台 <span>公开观测数据辅助研判 · 企业关联与适用依据由人员确认</span></footer>
    </Layout></Layout>
    <Drawer title="通知中心" open={notice} onClose={() => showNotice(false)}><QueryState query={notifications}>{notifications.data?.items.length ? notifications.data.items.map(n => <button className="notification-row" key={n.id} onClick={async () => { await markNotificationRead.mutateAsync({ id: n.id }); client.invalidateQueries({ queryKey: ['api'] }); navigate(link(n.href)); showNotice(false); }}><strong>{!n.read_at && <span className="live-dot" />}{n.title}</strong><p>{n.body}</p><small>{dateTime(n.created_at)}</small></button>) : <Empty description="暂无通知" />}</QueryState></Drawer>
    <JobDrawer id={jobId} onClose={() => setJobId('')} />
  </WorkbenchContext.Provider>;
}

function JobDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const job = useShellJob(id);
  const cancel = useCancelShellJob();
  return <Drawer title="任务进度" open={!!id} onClose={onClose}><QueryState query={job}>{job.data && <><div className="job-title"><h2>{labels[job.data.kind]}</h2><Status value={job.data.status} /></div><Progress percent={job.data.progress} status={job.data.status === 'failed' ? 'exception' : undefined} />{job.data.progress_stage && <p className="muted">{job.data.progress_stage}{job.data.progress_message ? `：${job.data.progress_message}` : ''}</p>}<dl className="detail-list"><dt>创建时间</dt><dd>{dateTime(job.data.created_at)}</dd><dt>任务编号</dt><dd className="mono">{id}</dd><dt>执行次数</dt><dd>{job.data.attempts}</dd></dl>{job.data.error && <p className="error-text">{job.data.error}</p>}{['queued', 'running'].includes(job.data.status) && <Button danger onClick={async () => { await cancel.mutateAsync({ id }); await job.refetch(); }}>取消任务</Button>}{job.data.download_available && <Button type="primary" icon={<DownloadOutlined />} href={`/api/v2/jobs/${id}/download`}>下载结果</Button>}<h3>执行结果</h3><pre className="json-detail">{JSON.stringify(job.data.result, null, 2)}</pre></>}</QueryState></Drawer>;
}
