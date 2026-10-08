import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Progress, Slider, Space, Table, Tag, Tooltip } from 'antd';
import { ArrowRightOutlined, CheckCircleFilled, CloseCircleFilled, ExclamationCircleFilled, PauseOutlined, PlusOutlined, ReloadOutlined, CaretRightOutlined } from '@ant-design/icons';
import type { EChartsOption } from 'echarts';
import { HOURS, NOW, aqiAt, calendar, cityAqiAt, cityMean, funnel, hours, ranking, stationById, stations, tasks } from '../mock';
import { useProto } from '../shell';
import { AqiBadge, AqiLegend, CalendarHeatmap, DataFreshness, DeadlineBar, EChart, MetricCard, SectionTitle, StationMap, StatusTag } from '../ui';
import { light } from '../tokens';

export function Dashboard() {
  const { role } = useProto();
  if (role === '执法人员') return <OfficerHome />;
  if (role === '研究者') return <ResearcherHome />;
  if (role === '管理员') return <AdminHome />;
  return <SupervisorHome />;
}

function PageHeading({ title, desc, extra }: { title: string; desc: string; extra?: React.ReactNode }) {
  return <div className="p-heading"><div><h1>{title}</h1><p>{desc}</p></div><Space>{extra}</Space></div>;
}

function useHourPlayer() {
  const [idx, setIdx] = useState(HOURS - 1);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setIdx(i => (i >= HOURS - 1 ? HOURS - 24 : i + 1)), 700);
    return () => clearInterval(t);
  }, [playing]);
  return { idx, setIdx, playing, setPlaying };
}

function SupervisorHome() {
  const player = useHourPlayer();
  const values = useMemo(() => Object.fromEntries(stations.map(s => [s.id, aqiAt(s.id, player.idx).aqi])), [player.idx]);
  const cityAqi = cityAqiAt();
  const rank = ranking('PM2.5').slice(0, 8);
  const cal = useMemo(() => calendar(120), []);
  const goodDays = cal.slice(-7).filter(([, v]) => v <= 100).length;
  const pmDaily = cityMean('PM2.5').filter((_, i) => i % 24 === 23).map(v => v ?? 0);
  const exceeded = rank.filter(r => r.ratio > 1);
  return (
    <>
      <PageHeading title="辖区态势总览" desc="掌握空气质量变化，让每一条异常都有可追溯的核查过程。" extra={<><Button icon={<ReloadOutlined />}>刷新</Button><Button type="primary" icon={<PlusOutlined />}>新建线索</Button></>} />
      <DataFreshness />
      <div className="p-metrics">
        <MetricCard label="全市当前 AQI" value={<AqiBadge aqi={cityAqi} size="lg" />} extra={<span className="muted">首要污染物 PM2.5</span>} hint="全市站点小时 AQI 均值，仅用于态势浏览" />
        <MetricCard label="近 7 天优良天数" value={goodDays} unit="/ 7 天" delta={-1} deltaGoodWhenDown={false} spark={cal.slice(-14).map(([, v]) => v)} to="/evaluations" />
        <MetricCard label="超限评价记录" value={12} unit="项" delta={3} tone="warn" spark={[3, 5, 2, 6, 4, 9, 12]} to="/evaluations" hint="站点 × 日期 × 污染物" />
        <MetricCard label="待办核查任务" value={8} unit="件" delta={-2} spark={[12, 11, 10, 10, 9, 10, 8]} to="/inspections" />
        <MetricCard label="整改超期" value={2} unit="件" tone="danger" extra={<Link to="/inspections/T-20260925-01">立即查看 <ArrowRightOutlined /></Link>} />
      </div>

      <div className="p-grid-main">
        <Card title="站点态势地图" extra={<AqiLegend />} className="p-card-map">
          <StationMap values={values} height={430} />
          <div className="p-player">
            <Button size="small" shape="circle" icon={player.playing ? <PauseOutlined /> : <CaretRightOutlined />} onClick={() => player.setPlaying(!player.playing)} aria-label="播放 24 小时回放" />
            <Slider min={HOURS - 24} max={HOURS - 1} value={player.idx} onChange={player.setIdx} tooltip={{ formatter: v => hours[v ?? 0].format('MM-DD HH:00') }} style={{ flex: 1 }} />
            <span className="p-player-time">{hours[player.idx].format('MM-DD HH:00')}</span>
          </div>
        </Card>
        <Card title="PM2.5 超限站点排行" extra={<span className="muted">近 24 小时均值 / 日均限值</span>}>
          <ol className="p-rank">
            {rank.map((r, i) => (
              <li key={r.station.id}>
                <span className={`p-rank-no ${i < 3 ? 'top' : ''}`}>{i + 1}</span>
                <Link to={`/stations/${r.station.id}`} className="p-rank-name">{r.station.name}<small>{r.station.district}</small></Link>
                <div className="p-rank-bar"><div style={{ width: `${Math.min(100, (r.ratio / rank[0].ratio) * 100)}%`, background: r.ratio > 1 ? light.danger : light.brand }} /></div>
                <b className={r.ratio > 1 ? 'is-over' : ''}>{r.ratio.toFixed(2)}×</b>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <div className="p-grid-2">
        <Card title="AQI 日历（近 120 天）" extra={<AqiLegend />}><CalendarHeatmap data={cal} height={200} /></Card>
        <Card title="核查进度漏斗" extra={<Link to="/inspections">全部任务</Link>}>
          <EChart label="核查进度漏斗" height={200} option={{
            tooltip: { trigger: 'item', formatter: '{b}：{c} 件' },
            series: [{ type: 'funnel', left: 10, right: 90, top: 6, bottom: 6, gap: 3, sort: 'none', minSize: '22%', data: funnel,
              label: { position: 'right', formatter: '{b}  {c}', color: light.text2 }, labelLine: { show: true, length: 12 },
              itemStyle: { borderWidth: 0 }, color: ['#9fd6d9', '#5fbcc2', '#2a9ba5', '#087f8c', '#05616b'] }],
          }} />
        </Card>
      </div>

      <Card title="需要关注的超限记录" className="p-mt" extra={<Space><span className="muted">PM2.5 · 近 7 天日均趋势</span><svg width="90" height="20" viewBox="0 0 90 20"><polyline fill="none" stroke={light.danger} strokeWidth="1.5" points={pmDaily.map((v, i) => `${(i / (pmDaily.length - 1)) * 90},${18 - (v / Math.max(...pmDaily)) * 16}`).join(' ')} /></svg></Space>}>
        <Table size="middle" rowKey={r => r.station.id} pagination={false} dataSource={exceeded} columns={[
          { title: '站点', render: (_, r) => <Link to={`/stations/${r.station.id}`}>{r.station.name}</Link> },
          { title: '区域', render: (_, r) => r.station.district },
          { title: '日期', render: () => NOW.subtract(1, 'day').format('YYYY-MM-DD') },
          { title: '污染物', render: () => 'PM2.5' },
          { title: '评价浓度', align: 'right', render: (_, r) => <span className="num">{r.mean} <small className="muted">μg/m³</small></span> },
          { title: '超限倍数', align: 'right', render: (_, r) => <b className="is-over num">{r.ratio.toFixed(2)}×</b> },
          { title: '线索', render: (_, r, i) => i % 2 ? <Tag bordered={false} color="processing">已生成</Tag> : <Button size="small" type="link" icon={<PlusOutlined />}>生成线索</Button> },
        ]} />
      </Card>
    </>
  );
}

function OfficerHome() {
  const mine = tasks.filter(t => t.owner === '李四').sort((a, b) => a.due.localeCompare(b.due));
  const area = stationById('s19');
  const values = useMemo(() => Object.fromEntries(stations.map(s => [s.id, aqiAt(s.id).aqi])), []);
  return (
    <>
      <PageHeading title="我的工作" desc="按截止时间排列的核查任务。现场录入支持平板拍照上传，草稿自动保存。" />
      <DataFreshness />
      <div className="p-grid-main">
        <Card title={<>我的任务 <Tag bordered={false}>{mine.length} 件</Tag></>} extra={<Link to="/inspections">全部任务</Link>}>
          <div className="p-task-list">
            {mine.map(t => (
              <Link key={t.id} to={`/inspections/${t.id}`} className={`p-task ${t.status === 'returned' ? 'is-returned' : ''}`}>
                <div className="p-task-main">
                  <div className="p-task-title"><StatusTag value={t.status} /><strong>{t.title}</strong></div>
                  <small>{t.enterprise} · {t.id} · 关联 {stationById(t.station).name} {t.pollutant}</small>
                </div>
                <div className="p-task-due"><DeadlineBar created={t.created} due={t.due} /><small>截止 {t.due}</small></div>
                <span className="p-task-go">进入 <ArrowRightOutlined /></span>
              </Link>
            ))}
          </div>
        </Card>
        <div className="p-stack">
          <Card title="负责区域当前空气">
            <div className="p-area">
              <AqiBadge aqi={values[area.id]} size="lg" />
              <div><strong>{area.district} · {area.name}</strong><small>首要污染物 {aqiAt(area.id).primary} · {NOW.format('HH:00')} 更新</small></div>
            </div>
            <StationMap values={values} height={220} selected={[area.id]} />
          </Card>
          <Card title="被退回的任务" extra={<Tag color="error" bordered={false}>1</Tag>}>
            {mine.filter(t => t.returnedNote).map(t => (
              <div key={t.id} className="p-returned">
                <strong>{t.title} · {t.enterprise}</strong>
                <blockquote>主管意见：{t.returnedNote}</blockquote>
                <Link to={`/inspections/${t.id}`}>去补充 <ArrowRightOutlined /></Link>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </>
  );
}

function ResearcherHome() {
  const quality: EChartsOption = {
    grid: { left: 60, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { type: 'dashed', color: light.borderWeak } } },
    yAxis: { type: 'category', data: ['CO', 'SO2', 'NO2', 'O3', 'PM10', 'PM2.5'], axisTick: { show: false } },
    tooltip: { trigger: 'axis' },
    series: [
      { type: 'bar', name: '有效', stack: 'q', data: [97.1, 96.4, 97.9, 98.2, 96.8, 97.5], itemStyle: { color: light.brand }, barWidth: 14 },
      { type: 'bar', name: '缺失', stack: 'q', data: [2.2, 2.9, 1.6, 1.3, 2.6, 2.1], itemStyle: { color: '#c9d5da' } },
      { type: 'bar', name: '无效', stack: 'q', data: [0.7, 0.7, 0.5, 0.5, 0.6, 0.4], itemStyle: { color: light.danger } },
    ],
    legend: { bottom: 0, right: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10 },
  };
  const models = [
    { key: 1, name: 'seasonal', task: '预测', mae: 8.4, rmse: 12.1, cover: '88%', status: 'active' },
    { key: 2, name: 'LightGBM', task: '预测', mae: 8.9, rmse: 12.8, cover: '84%', status: 'blocked' },
    { key: 3, name: 'interpolation', task: '插补', mae: 5.2, rmse: 7.9, cover: '—', status: 'active' },
    { key: 4, name: 'SAITS', task: '插补', mae: 5.6, rmse: 8.4, cover: '—', status: 'blocked' },
    { key: 5, name: 'BRITS', task: '插补', mae: 5.9, rmse: 8.8, cover: '—', status: 'blocked' },
  ];
  return (
    <>
      <PageHeading title="数据与模型" desc="观测完整性、插补占比与候选模型评估。研究者视角不包含企业证据。" />
      <DataFreshness />
      <div className="p-metrics p-metrics-4">
        <MetricCard label="观测有效率" value="97.3" unit="%" delta={0.4} deltaGoodWhenDown={false} spark={[96.1, 96.8, 97.0, 96.5, 97.2, 97.1, 97.3]} />
        <MetricCard label="插补辅助值占比" value="2.1" unit="%" hint="插补值单独存储，不覆盖原始观测" />
        <MetricCard label="已激活模型" value={2} unit="/ 5 候选" extra={<span className="muted">未超过基线的候选不发布</span>} />
        <MetricCard label="数据快照" value={14} unit="个" extra={<span className="muted">最新 10-08</span>} />
      </div>
      <div className="p-grid-2">
        <Card title="六项污染物数据质量"><EChart label="数据质量" option={quality} height={260} /></Card>
        <Card title="候选模型评估（原尺度，测试集）" extra={<Link to="/models">模型中心</Link>}>
          <Table size="small" pagination={false} dataSource={models} columns={[
            { title: '模型', dataIndex: 'name', render: v => <code>{v}</code> }, { title: '任务', dataIndex: 'task' },
            { title: 'MAE', dataIndex: 'mae', align: 'right' }, { title: 'RMSE', dataIndex: 'rmse', align: 'right' }, { title: '90% 区间覆盖', dataIndex: 'cover', align: 'right' },
            { title: '发布门禁', dataIndex: 'status', render: v => v === 'active' ? <Tag color="success" bordered={false}>已激活</Tag> : <Tooltip title="未超过基线，保持未激活"><Tag bordered={false}>未通过</Tag></Tooltip> },
          ]} />
        </Card>
      </div>
    </>
  );
}

function AdminHome() {
  const services = [
    ['API', 'ok', '响应 42ms'], ['IO Worker', 'ok', '队列 0'], ['模型 Worker', 'ok', '空闲'], ['调度器', 'ok', '下次 03:30'],
    ['PostgreSQL', 'ok', '连接 18/30'], ['Redis', 'ok', '内存 61MB'], ['备份', 'warn', '最近 2 天前'], ['数据源', 'ok', '试运行授权 剩 83 天'],
  ] as const;
  const gates = [
    ['七天在线窗口', true], ['采集覆盖率', false], ['数据源许可', true], ['备份与恢复核验', false], ['生产签署', false],
  ] as const;
  const days = Array.from({ length: 14 }, (_, i) => ({ d: NOW.subtract(13 - i, 'day'), s: i === 4 ? 'failed' : i === 9 ? 'partial' : 'succeeded' }));
  return (
    <>
      <PageHeading title="系统运行" desc="服务健康、采集任务与上线门禁。" />
      <div className="p-services">
        {services.map(([n, s, d]) => (
          <div key={n} className={`p-service ${s}`}>
            {s === 'ok' ? <CheckCircleFilled /> : <ExclamationCircleFilled />}<div><strong>{n}</strong><small>{d}</small></div>
          </div>
        ))}
      </div>
      <div className="p-grid-2">
        <Card title="近 14 天采集任务" extra={<span className="muted">每日 03:30 · 重查前七天</span>}>
          <div className="p-collect-days">
            {days.map(({ d, s }) => (
              <Tooltip key={d.format('MMDD')} title={`${d.format('MM-DD')} ${s === 'succeeded' ? '成功' : s === 'partial' ? '部分成功：extra 文件 404' : '失败：来源超时，已重试 3 次'}`}>
                <div className={`p-collect-day ${s}`}><span>{d.format('DD')}</span></div>
              </Tooltip>
            ))}
          </div>
          <SectionTitle style={{ marginTop: 18 }}>任务队列</SectionTitle>
          <Table size="small" pagination={false} rowKey="id" dataSource={[
            { id: 'J-8812', kind: '在线采集', status: 'succeeded', p: 100, t: '03:30' }, { id: 'J-8813', kind: '标准评价', status: 'succeeded', p: 100, t: '03:42' },
            { id: 'J-8814', kind: '趋势预测', status: 'running', p: 64, t: '13:58' }, { id: 'J-8815', kind: '报告导出', status: 'queued', p: 0, t: '14:01' },
          ]} columns={[
            { title: '编号', dataIndex: 'id', render: v => <code>{v}</code> }, { title: '类型', dataIndex: 'kind' }, { title: '提交', dataIndex: 't' },
            { title: '进度', dataIndex: 'p', width: 180, render: (v, r) => <Progress percent={v} size="small" status={r.status === 'running' ? 'active' : undefined} /> },
          ]} />
        </Card>
        <Card title="上线门禁" extra={<Tag color="warning" bordered={false}>未完成</Tag>}>
          <ul className="p-gates">
            {gates.map(([n, ok]) => <li key={n} className={ok ? 'ok' : ''}>{ok ? <CheckCircleFilled /> : <CloseCircleFilled />}<span>{n}</span><small>{ok ? '已通过' : '未通过'}</small></li>)}
          </ul>
          <p className="muted p-note">门禁结果由只读验收报告生成，不能通过修改环境变量或伪造任务记录通过。</p>
        </Card>
      </div>
    </>
  );
}
