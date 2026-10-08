import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Empty, Space, Table, Tag } from 'antd';
import { ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { dateTime, number, queryString } from '../../shared/api';
import type { Evaluation, Inspection, Page, Row } from '../../shared/api';
import { Heading, QueryState, Status } from '../../shared/components';
import { useWorkbench } from '../../shared/context';
import { AqiBadge, AqiLegend, CalendarHeatmap, DataFreshness, DeadlineBar, MetricCard, StationMap } from '../../shared/ui';
import { unit } from './pages';
import { useMonitoringQuery } from './hooks';

type Snapshot = { station_id: string; name: string; latitude?: number | null; longitude?: number | null; aqi?: number | null; local_date?: string | null; primary?: string | null };

export function Workspace() {
  const { start, end, city, link, user } = useWorkbench();
  const navigate = useNavigate();
  const dashboard = useMonitoringQuery(`/dashboard?${queryString({ start, end, city_id: city })}`);
  const exceedances = useMonitoringQuery<Page<Evaluation>>(`/evaluations?${queryString({ start, end, city_id: city, status: 'exceeded', page_size: 8 })}`);
  const tasks = useMonitoringQuery<Page<Inspection>>('/inspections?page_size=5', user.role !== '研究者');
  const aqiDaily = useMonitoringQuery(`/timeseries?${queryString({ start: dayjs(start).subtract(110, 'day').format('YYYY-MM-DD'), end, city_id: city, pollutant: 'AQI', resolution: 'day' })}`);
  const data = dashboard.data as (Row & { station_snapshot?: Snapshot[] }) | undefined;
  const snapshot = useMemo(() => (data?.station_snapshot ?? []).filter(s => s.latitude != null && s.longitude != null), [data]);
  const cityAqi = useMemo(() => {
    const vals = snapshot.map(s => s.aqi).filter((v): v is number => v != null);
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
  }, [snapshot]);
  const calendarData = useMemo<[string, number][]>(() =>
    (aqiDaily.data?.items ?? []).map((p: Row) => [dayjs(p.time).format('YYYY-MM-DD'), Math.round(p.value)]), [aqiDaily.data]);
  const quality = data?.pollutants?.reduce((s: Row, p: Row) => ({ valid: s.valid + p.valid, total: s.total + p.total }), { valid: 0, total: 0 });
  const goodDays = calendarData.slice(-7).filter(([, v]) => v <= 100).length;
  const exceededRows = (exceedances.data?.items ?? []).slice().sort((a, b) => (b.exceed_ratio ?? 0) - (a.exceed_ratio ?? 0));
  const taskItems = (tasks.data?.items ?? []).slice().sort((a, b) => String(a.due_date ?? '9999').localeCompare(String(b.due_date ?? '9999')));

  const metrics = (
    <div className={`ws-metrics ${user.role === '研究者' ? 'ws-metrics-4' : ''}`}>
      <MetricCard label="全市当前 AQI" value={<AqiBadge aqi={cityAqi} size="lg" />} extra={<span className="muted">{cityAqi != null ? `首要污染物 ${snapshot.find(s => s.aqi === cityAqi)?.primary ?? '—'}` : '暂无站点评价'}</span>} hint="各站点最近一日 AQI 评价均值，仅用于态势浏览" />
      <MetricCard label="近 7 天优良天数" value={calendarData.length ? goodDays : '—'} unit={calendarData.length ? '/ 7 天' : ''} spark={calendarData.slice(-14).map(([, v]) => v)} to={link('/evaluations')} />
      <MetricCard label="超限评价记录" value={number(data?.evaluations?.exceeded, 0)} unit="项" tone={data?.evaluations?.exceeded ? 'warn' : undefined} to={link('/evaluations?status=exceeded')} hint="站点 × 日期 × 污染物" />
      {user.role !== '研究者'
        ? <MetricCard label="待办核查任务" value={number(data?.pending_inspections, 0)} unit="件" to={link('/inspections')} />
        : <MetricCard label="数据不足记录" value={number(data?.evaluations?.insufficient, 0)} unit="项" to={link('/evaluations?status=insufficient')} hint="完整性不足时不作达标结论" />}
      <MetricCard label="有效站点目录" value={number(data?.stations, 0)} unit="个" to={link('/monitoring')} hint="当前启用的监测站点" />
    </div>
  );

  const taskCard = user.role !== '研究者' && (
    <Card title={<>核查待办 <Tag bordered={false}>{data?.pending_inspections ?? 0}</Tag></>} extra={<Link to={link('/inspections')}>任务列表</Link>}>
      <QueryState query={tasks}>
        {taskItems.length ? taskItems.map(t => (
          <Link className="task-row-v2" key={t.id} to={link(`/inspections/${t.id}`)}>
            <div><div className="task-title"><Status value={t.status} /><strong>{t.title}</strong></div>
              <small>{t.id}</small></div>
            {t.due_date ? <DeadlineBar created={t.created_at} due={t.due_date} compact /> : <span className="muted">未设期限</span>}
            <span className="task-go">进入 <ArrowRightOutlined /></span>
          </Link>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待办核查任务" />}
      </QueryState>
    </Card>
  );

  const mapCard = (
    <Card title="站点态势" extra={<AqiLegend />}>
      {snapshot.length
        ? <StationMap items={snapshot.map(s => ({ id: s.station_id, name: s.name, latitude: s.latitude, longitude: s.longitude, aqi: s.aqi, primary: s.primary }))} height={430}
            onSelect={s => navigate(link(`/stations/${s.id}`))} />
        : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="站点暂无坐标或评价数据" />}
      <p className="card-footnote">点位按各站点最近一日 AQI 评价着色；正式版叠加政务网天地图底图。</p>
    </Card>
  );

  const rankCard = (
    <Card title="超限评价记录" extra={<Link to={link('/evaluations?status=exceeded')}>查看全部</Link>}>
      <QueryState query={exceedances} empty={!exceededRows.length}>
        <Table size="small" pagination={false} rowKey="id" dataSource={exceededRows} columns={[
          { title: '站点 / 日期', render: (_, r) => <Link to={link(`/stations/${r.station_id}`)}>{String(r.station_name)}<small className="block muted">{r.local_date}</small></Link> },
          { title: '污染物', dataIndex: 'pollutant', width: 80 },
          { title: '评价浓度', align: 'right', render: (_, r) => `${number(r.value)} ${unit(r.pollutant)}` },
          { title: '超标倍数', align: 'right', width: 90, render: (_, r) => <b className="is-over">{number(r.exceed_ratio, 2)}×</b> },
        ]} />
      </QueryState>
    </Card>
  );

  const calendarCard = (
    <Card title="AQI 日历（全市均值）" extra={<AqiLegend />}>
      {calendarData.length ? <CalendarHeatmap data={calendarData} height={200} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="所选时段暂无 AQI 评价数据" />}
    </Card>
  );

  return <>
    <Heading title={user.role === '执法人员' ? '我的工作' : '辖区态势总览'} eyebrow="WORKSPACE OVERVIEW"
      description="掌握空气质量变化，让每一条异常都有可追溯的核查过程。"
      extra={<Button icon={<ReloadOutlined />} onClick={() => dashboard.refetch()}>刷新总览</Button>} />
    <QueryState query={dashboard}>
      <DataFreshness stale={data?.stale} latest={data?.latest_date ? String(data.latest_date) : null}
        ingested={dateTime(data?.updated_at)} source={data?.attribution}
        mode={String(data?.attribution ?? '').includes('Quotsoft') ? '试运行数据源' : undefined} />
      {metrics}
      {user.role === '执法人员' && <div className="ws-grid-2">{taskCard}{mapCard}</div>}
      {user.role !== '执法人员' && (
        <div className="ws-grid-main">{mapCard}
          <Space direction="vertical" size={16} style={{ width: '100%' }}>{rankCard}</Space>
        </div>
      )}
      <div className="ws-grid-2">{calendarCard}{user.role === '执法人员' ? rankCard : taskCard}</div>
    </QueryState>
  </>;
}
