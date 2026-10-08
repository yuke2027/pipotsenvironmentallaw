import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { App, Button, Card, Segmented, Select, Space, Switch, Table, Tabs, Tag, Tooltip } from 'antd';
import { DownloadOutlined, EnvironmentOutlined, StarOutlined, SyncOutlined, PlusOutlined } from '@ant-design/icons';
import type { EChartsOption } from 'echarts';
import { HOURS, NOW, aqiAt, calendar, forecast, hours, limits, pollutantNames, pollutants, series, stationById, stations, unit } from '../mock';
import type { Pollutant } from '../mock';
import { AqiBadge, AqiLegend, CalendarHeatmap, DataFreshness, EChart, StationMap, TrustLegend } from '../ui';
import { light, seriesPalette, trust } from '../tokens';

const splitLine = { lineStyle: { type: 'dashed' as const, color: light.borderWeak } };

function gaps(values: (number | null)[]) {
  const areas: [{ xAxis: number }, { xAxis: number }][] = [];
  values.forEach((v, i) => { if (v == null) areas.push([{ xAxis: hours[Math.max(0, i - 1)].valueOf() }, { xAxis: hours[Math.min(HOURS - 1, i + 1)].valueOf() }]); });
  return areas;
}

export function Monitoring() {
  const { message } = App.useApp();
  const [pollutant, setPollutant] = useState<Pollutant>('PM2.5');
  const [selected, setSelected] = useState<string[]>(['s01', 's19', 's33']);
  const [resolution, setResolution] = useState<'hour' | 'day'>('hour');
  const [showImputed, setShowImputed] = useState(true);
  const values = useMemo(() => Object.fromEntries(stations.map(s => [s.id, aqiAt(s.id).aqi])), []);
  const toggle = (id: string) => setSelected(sel => sel.includes(id) ? sel.filter(x => x !== id) : sel.length >= 5 ? (message.warning('最多同时对比 5 个站点'), sel) : [...sel, id]);

  const option = useMemo<EChartsOption>(() => {
    const lines = selected.map((id, k) => {
      const { values: v, imputed } = series(id, pollutant);
      const data = resolution === 'hour'
        ? v.map((y, i) => [hours[i].valueOf(), y])
        : Array.from({ length: 7 }, (_, d) => {
          const day = v.slice(d * 24, d * 24 + 24).filter((x): x is number => x != null);
          return [hours[d * 24].startOf('day').valueOf(), day.length >= 20 ? Math.round(day.reduce((a, b) => a + b, 0) / day.length) : null];
        });
      return [
        { type: 'line' as const, name: stationById(id).name, data, showSymbol: resolution === 'day', connectNulls: false, lineStyle: { width: 2 }, color: seriesPalette[k],
          markArea: k === 0 && resolution === 'hour' ? { silent: true, itemStyle: { color: '#b9c6cc33' }, data: gaps(v) } : undefined,
          markLine: k === 0 ? { silent: true, symbol: 'none', lineStyle: { color: light.danger, type: 'dashed' as const }, label: { formatter: `限值 ${limits[pollutant]}`, color: light.danger, fontSize: 11, position: 'insideEndTop' as const }, data: [{ yAxis: limits[pollutant] }] } : undefined },
        ...(showImputed && resolution === 'hour' ? [{ type: 'scatter' as const, name: `${stationById(id).name} · 插补`, symbol: 'diamond', symbolSize: 8, itemStyle: { color: trust.imputed.color },
          data: imputed.map(([i, y]) => [hours[i].valueOf(), y]) }] : []),
      ];
    }).flat();
    return {
      grid: { left: 48, right: 24, top: 40, bottom: 58 },
      legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, data: selected.map(id => stationById(id).name) },
      xAxis: { type: 'time', axisLine: { lineStyle: { color: light.border } }, axisLabel: { color: light.text3 } },
      yAxis: { type: 'value', name: unit(pollutant), nameTextStyle: { color: light.text3 }, splitLine },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8, borderColor: light.border, fillerColor: '#087f8c1a' }],
      series: lines,
    };
  }, [selected, pollutant, resolution, showImputed]);

  const first = selected[0] ?? 's01';
  const detail = useMemo(() => {
    const { values: v, imputed } = series(first, pollutant);
    return Array.from({ length: 24 }, (_, k) => {
      const i = HOURS - 1 - k;
      const imp = imputed.find(([x]) => x === i);
      return { key: i, time: hours[i].format('YYYY-MM-DD HH:00'), value: v[i], imputed: imp?.[1], revised: i % 37 === 0, file: `beijing/${hours[i].format('YYYY-MM-DD')}/${['PM2.5', 'PM10'].includes(pollutant) ? 'all' : 'extra'}` };
    });
  }, [first, pollutant]);

  const matrix = useMemo<EChartsOption>(() => {
    const span = 72;
    const data: [number, number, number | null][] = [];
    stations.forEach((s, y) => series(s.id, pollutant).values.slice(-span).forEach((v, x) => data.push([x, y, v])));
    const max = limits[pollutant] * 1.4;
    return {
      tooltip: { trigger: 'item', formatter: (p: any) => `${stations[p.data[1]].name}<br/>${hours[HOURS - span + p.data[0]].format('MM-DD HH:00')}<br/>${p.data[2] ?? '缺失'} ${p.data[2] != null ? unit(pollutant) : ''}` },
      grid: { left: 96, right: 70, top: 8, bottom: 30 },
      xAxis: { type: 'category', data: hours.slice(-span).map(h => h.format('MM-DD HH时')), axisLabel: { interval: 11, color: light.text3, fontSize: 10 }, axisTick: { show: false }, axisLine: { show: false } },
      yAxis: { type: 'category', data: stations.map(s => s.name), axisLabel: { fontSize: 10, color: light.text2 }, axisTick: { show: false }, axisLine: { show: false } },
      visualMap: { min: 0, max, calculable: true, orient: 'vertical', right: 0, top: 'middle', itemHeight: 160, inRange: { color: ['#e4f4f3', '#7ccac6', '#f4c95d', '#e8743b', '#a3263a'] }, textStyle: { color: light.text3 } },
      series: [{ type: 'heatmap', data, itemStyle: { borderColor: '#fff', borderWidth: 1 }, emphasis: { itemStyle: { borderColor: light.text1 } } }],
    };
  }, [pollutant]);

  return (
    <>
      <div className="p-heading"><div><h1>监测分析</h1><p>从趋势到每一条观测，核对数据来源、缺失状态与统计口径。</p></div>
        <Space><Button icon={<StarOutlined />}>保存为常用筛选</Button><Button icon={<DownloadOutlined />} type="primary">导出当前查询</Button></Space></div>
      <DataFreshness />
      <Card className="p-filter">
        <label>污染物<Select value={pollutant} onChange={setPollutant} style={{ width: 150 }} options={pollutants.map(p => ({ value: p, label: `${p} ${pollutantNames[p]}` }))} /></label>
        <label className="grow">对比站点（最多 5 个，可在地图上点选）
          <Select mode="multiple" value={selected} onChange={v => v.length <= 5 && setSelected(v)} maxTagCount="responsive" showSearch optionFilterProp="label"
            options={stations.map(s => ({ value: s.id, label: s.name }))} style={{ width: '100%' }} />
        </label>
        <label>时间粒度<Segmented value={resolution} onChange={v => setResolution(v as 'hour' | 'day')} options={[{ label: '小时', value: 'hour' }, { label: '日均', value: 'day' }]} /></label>
        <label>插补辅助值<Switch checked={showImputed} onChange={setShowImputed} disabled={resolution === 'day'} /></label>
        <div className="p-saved"><span>常用：</span><Tag bordered={false} color="processing">城区三站 PM2.5</Tag><Tag bordered={false}>南部 O3</Tag></div>
      </Card>
      <div className="p-grid-map-chart">
        <Card title={<><EnvironmentOutlined /> 站点分布</>} extra={<AqiLegend />}>
          <StationMap values={values} selected={selected} onSelect={s => toggle(s.id)} height={400} />
        </Card>
        <Card title={`${pollutant} 浓度变化`} extra={<TrustLegend items={['measured', 'imputed', 'missing']} />}>
          <EChart option={option} height={400} label={`${pollutant} 多站点浓度对比`} />
        </Card>
      </div>
      <Card className="p-mt">
        <Tabs items={[
          { key: 'obs', label: '原始观测明细', children: (
            <Table size="middle" pagination={{ pageSize: 8, showTotal: t => `共 ${t} 条` }} dataSource={detail} columns={[
              { title: '观测时间（北京）', dataIndex: 'time', width: 170 },
              { title: '站点', render: () => <Link to={`/stations/${first}`}>{stationById(first).name}</Link> },
              { title: '污染物', render: () => pollutant },
              { title: '原始值', align: 'right', render: (_, r) => r.value == null ? <span className="muted">—</span> : <span className="num">{r.value} <small className="muted">{unit(pollutant)}</small></span> },
              { title: '质量', render: (_, r) => r.value == null ? <Tag bordered={false}>缺失</Tag> : <Tag bordered={false} color="success">有效</Tag> },
              { title: '插补辅助值', align: 'right', render: (_, r) => r.imputed != null ? <span className="imputed-cell">◆ {r.imputed}</span> : '' },
              { title: '口径', render: () => '小时值' },
              { title: '来源文件', dataIndex: 'file', render: (v, r) => <span className="mono">{v}{r.revised && <Tooltip title="该日文件存在修订，已采用当前修订"><SyncOutlined className="revised-icon" /></Tooltip>}</span> },
            ]} />) },
          { key: 'matrix', label: '站点 × 时间热力矩阵', children: <EChart option={matrix} height={720} label="站点时间热力矩阵" /> },
          { key: 'quality', label: '数据质量', children: <QualityBars pollutant={pollutant} /> },
          { key: 'files', label: '来源文件与修订', children: (
            <Table size="small" pagination={false} rowKey="k" dataSource={Array.from({ length: 6 }, (_, i) => ({ k: i, d: NOW.subtract(i, 'day').format('YYYY-MM-DD'), kind: i % 2 ? 'extra' : 'all', rev: i === 2 ? 2 : 1, sha: (0x3fa2c1 * (i + 7)).toString(16).padEnd(12, '0').slice(0, 12) }))} columns={[
              { title: '日期', dataIndex: 'd' }, { title: '类型', dataIndex: 'kind', render: v => v === 'all' ? '颗粒物与 AQI' : '气态污染物' },
              { title: '修订', dataIndex: 'rev', render: v => v > 1 ? <Tag color="gold" bordered={false}>第 {v} 版 · 当前</Tag> : <Tag bordered={false}>第 1 版</Tag> },
              { title: 'SHA-256', dataIndex: 'sha', render: v => <code>{v}…</code> }, { title: '获取时间', render: (_, r) => `${r.d} 03:3${r.k}` },
            ]} />) },
        ]} />
      </Card>
    </>
  );
}

function QualityBars({ pollutant }: { pollutant: Pollutant }) {
  const rows = stations.map(s => {
    const v = series(s.id, pollutant).values;
    return { name: s.name, valid: Math.round((v.filter(x => x != null).length / v.length) * 1000) / 10 };
  }).sort((a, b) => a.valid - b.valid);
  return <EChart label="站点有效率" height={640} option={{
    grid: { left: 100, right: 40, top: 10, bottom: 20 },
    xAxis: { type: 'value', min: 90, max: 100, axisLabel: { formatter: '{value}%' }, splitLine },
    yAxis: { type: 'category', data: rows.map(r => r.name), axisTick: { show: false }, axisLabel: { fontSize: 11 } },
    series: [{ type: 'bar', data: rows.map(r => ({ value: r.valid, itemStyle: { color: r.valid < 97 ? light.warning : light.brand, borderRadius: [0, 3, 3, 0] } })), barWidth: 10,
      label: { show: true, position: 'right', formatter: '{c}%', fontSize: 10, color: light.text3 } }],
  }} />;
}

export function StationDetail() {
  const { id = 's01' } = useParams();
  const s = stationById(id);
  const { aqi, primary } = aqiAt(s.id);
  const [fcP, setFcP] = useState<Pollutant>('PM2.5');
  const fc = useMemo(() => forecast(s.id, fcP), [s.id, fcP]);
  const hist = series(s.id, fcP).values.map((v, i) => [hours[i].valueOf(), v]);
  const fcOption: EChartsOption = {
    grid: { left: 48, right: 24, top: 40, bottom: 36 },
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, data: ['实测', '预测', '90% 区间'] },
    xAxis: { type: 'time', axisLabel: { color: light.text3 } },
    yAxis: { type: 'value', name: unit(fcP), splitLine },
    series: [
      { type: 'line', name: '实测', data: hist, showSymbol: false, connectNulls: false, color: trust.measured.color, lineStyle: { width: 2 },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: light.text3 }, label: { formatter: '现在', color: light.text2 }, data: [{ xAxis: NOW.valueOf() }] } },
      { type: 'line', name: '区间下界', data: fc.map(p => [p.time.valueOf(), p.lo]), stack: 'band', showSymbol: false, lineStyle: { opacity: 0 }, tooltip: { show: false } },
      { type: 'line', name: '90% 区间', data: fc.map(p => [p.time.valueOf(), p.hi - p.lo]), stack: 'band', showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color: '#3b6fd822' }, color: '#3b6fd855' },
      { type: 'line', name: '预测', data: [[hours[HOURS - 1].valueOf(), hist[HOURS - 1][1]], ...fc.map(p => [p.time.valueOf(), p.value])], showSymbol: false, color: trust.forecast.color, lineStyle: { type: 'dashed', width: 2 } },
    ],
    dataZoom: [{ type: 'inside', startValue: NOW.subtract(72, 'hour').valueOf() }],
  };
  return (
    <>
      <div className="p-station-head">
        <AqiBadge aqi={aqi} size="lg" />
        <div className="grow">
          <h1>{s.name}{s.control && <Tag className="p-ml" bordered={false}>对照点</Tag>}</h1>
          <p className="muted">{s.district} · {s.lon.toFixed(3)}, {s.lat.toFixed(3)}（示例坐标）· 首要污染物 {primary} · {NOW.format('MM-DD HH:00')} 更新</p>
        </div>
        <Space><Button icon={<PlusOutlined />}>加入对比</Button><Button icon={<DownloadOutlined />}>导出</Button></Space>
      </div>
      <div className="p-pollutant-cards">
        {pollutants.map(p => {
          const v = series(s.id, p).values;
          const cur = [...v].reverse().find(x => x != null) ?? 0;
          const ratio = cur / limits[p];
          return (
            <div key={p} className="p-pollutant-card">
              <div><strong>{p}</strong><small>{pollutantNames[p]}</small></div>
              <b className="num">{cur}<small>{unit(p)}</small></b>
              <div className="p-level-track"><div style={{ width: `${Math.min(100, ratio * 100)}%`, background: ratio > 1 ? light.danger : ratio > 0.75 ? light.warning : light.brand }} /></div>
              <small className="muted">限值 {limits[p]} · {Math.round(ratio * 100)}%</small>
            </div>
          );
        })}
      </div>
      <Card title="实测与 24 小时预测" className="p-mt" extra={<Space><Segmented size="small" value={fcP} onChange={v => setFcP(v as Pollutant)} options={['PM2.5', 'PM10']} /><Tag bordered={false}>模型 seasonal · v3 · 已激活</Tag></Space>}>
        <EChart option={fcOption} height={340} label="实测与预测" />
        <p className="p-note muted">预测为辅助研判信息，区间为名义 90%。历史回测覆盖率 88%，不作为执法依据。</p>
      </Card>
      <div className="p-grid-2 p-mt">
        <Card title="本站 AQI 日历" extra={<AqiLegend />}><CalendarHeatmap data={calendar(120, s.id)} height={200} /></Card>
        <Card title="本站标准评价记录">
          <Table size="small" pagination={false} rowKey="d" dataSource={Array.from({ length: 6 }, (_, i) => {
            const d = NOW.subtract(i + 1, 'day'); const v = Math.round(40 + ((i * 37 + s.id.charCodeAt(2)) % 60));
            return { d: d.format('MM-DD'), p: i % 3 === 2 ? 'O3' : 'PM2.5', v, st: i === 4 ? 'insufficient' : v > 75 ? 'exceeded' : 'within' };
          })} columns={[
            { title: '日期', dataIndex: 'd' }, { title: '污染物', dataIndex: 'p' }, { title: '评价浓度', dataIndex: 'v', align: 'right' },
            { title: '结论', dataIndex: 'st', render: v => <Tag bordered={false} color={v === 'exceeded' ? 'error' : v === 'within' ? 'success' : 'default'}>{v === 'exceeded' ? '超过限值' : v === 'within' ? '未超限' : '数据不足（<20 小时）'}</Tag> },
          ]} />
        </Card>
      </div>
    </>
  );
}
