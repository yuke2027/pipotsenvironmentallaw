import { useEffect, useMemo, useRef } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Tag, Tooltip } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined, InfoCircleOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import { aqiLevel, aqiLevels, dark, font, light, seriesPalette, statusColors, trust } from './tokens';
import { NOW, source, stations } from './mock';
import type { Station } from './mock';

/* ---------- ECharts 容器：统一主题、自适应与销毁 ---------- */
export function EChart({ option, height = 300, theme = 'light', onClick, label }: {
  option: EChartsOption; height?: number | string; theme?: 'light' | 'dark'; onClick?: (p: any) => void; label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const click = useRef(onClick);
  click.current = onClick;
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.on('click', p => click.current?.(p));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.dispose(); };
  }, []);
  useEffect(() => {
    const chart = ref.current && echarts.getInstanceByDom(ref.current);
    if (!chart) return;
    const t = theme === 'dark' ? dark : light;
    chart.setOption({
      color: seriesPalette, animationDuration: 400,
      textStyle: { fontFamily: font.family, color: t.text2 },
      tooltip: { trigger: 'axis', confine: true, backgroundColor: theme === 'dark' ? '#0b2230ee' : '#fff', borderColor: t.border, textStyle: { color: t.text1 } },
      ...option,
    }, true);
  }, [option, theme]);
  return <div ref={ref} role="img" aria-label={label} style={{ height, width: '100%' }} />;
}

/* ---------- AQI 徽标：色块 + 等级文字 + 数值，不只依赖颜色 ---------- */
export function AqiBadge({ aqi, size = 'md', showLabel = true }: { aqi: number; size?: 'sm' | 'md' | 'lg'; showLabel?: boolean }) {
  const l = aqiLevel(aqi);
  return (
    <span className={`aqi-badge aqi-${size}`} style={{ background: l.color, color: l.text }} title={`AQI ${aqi} · ${l.full}`}>
      {showLabel && <em>{l.name}</em>}<b>{aqi}</b>
    </span>
  );
}
export function AqiLegend({ darkMode }: { darkMode?: boolean }) {
  return (
    <div className={`aqi-legend ${darkMode ? 'is-dark' : ''}`}>
      {aqiLevels.map(l => <span key={l.name}><i style={{ background: l.color }} />{l.name}</span>)}
    </div>
  );
}

/* ---------- 业务状态标签 ---------- */
export function StatusTag({ value }: { value: string }) {
  const s = statusColors[value] ?? { label: value, color: light.text3 };
  return <span className="status-tag" style={{ color: s.color, background: `${s.color}14`, borderColor: `${s.color}40` }}><i style={{ background: s.color }} />{s.label}</span>;
}

/* ---------- 数据可信度图例 ---------- */
export function TrustLegend({ items = ['measured', 'imputed', 'forecast', 'missing'] as (keyof typeof trust)[] }) {
  return (
    <div className="trust-legend">
      {items.map(k => <span key={k} className={`trust-${k}`}><i style={{ background: trust[k].color }} />{trust[k].label}</span>)}
    </div>
  );
}

/* ---------- 数据新鲜度条：来源由接口提供，不写死 ---------- */
export function DataFreshness() {
  const stale = source.delayHours > 3;
  return (
    <div className={`freshness ${stale ? 'is-stale' : ''}`}>
      <span className={stale ? 'dot warn' : 'dot live'} />
      <strong>{stale ? `数据延迟 ${source.delayHours} 小时` : '观测数据已更新'}</strong>
      <span>最新观测 {source.latestObservation.format('MM-DD HH:mm')}</span>
      <span className="sep">·</span>
      <span>入库 {source.ingestedAt.format('MM-DD HH:mm')}</span>
      <span className="sep">·</span>
      <span>来源：{source.name}</span>
      <Tag color="gold" bordered={false} className="freshness-mode">{source.mode}</Tag>
    </div>
  );
}

/* ---------- 指标卡 ---------- */
export function MetricCard({ label, value, unit, delta, deltaGoodWhenDown = true, spark, to, tone, extra, hint }: {
  label: string; value: ReactNode; unit?: string; delta?: number; deltaGoodWhenDown?: boolean; spark?: number[];
  to?: string; tone?: 'warn' | 'danger'; extra?: ReactNode; hint?: string;
}) {
  const good = delta == null ? undefined : deltaGoodWhenDown ? delta <= 0 : delta >= 0;
  const body = (
    <>
      <div className="metric-label">{label}{hint && <Tooltip title={hint}><InfoCircleOutlined /></Tooltip>}</div>
      <div className="metric-value">{value}{unit && <small>{unit}</small>}</div>
      <div className="metric-foot">
        {delta != null && <span className={good ? 'delta good' : 'delta bad'}>{delta > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}{Math.abs(delta)} 较上周期</span>}
        {extra}
      </div>
      {spark && <Spark data={spark} color={tone === 'danger' ? light.danger : tone === 'warn' ? light.warning : light.brand} />}
    </>
  );
  const cls = `metric-card ${tone ? `tone-${tone}` : ''}`;
  return to ? <Link to={to} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
}
function Spark({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data), min = Math.min(...data);
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * 100},${28 - ((v - min) / Math.max(1, max - min)) * 24}`).join(' ');
  return <svg className="spark" viewBox="0 0 100 30" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" /></svg>;
}

/* ---------- 期限条 ---------- */
export function DeadlineBar({ created, due, compact }: { created: string; due: string; compact?: boolean }) {
  const total = Math.max(1, NOW.startOf('day').diff(created, 'day') + Math.max(0, -NOW.startOf('day').diff(due, 'day')));
  const left = -NOW.startOf('day').diff(due, 'day');
  const pct = Math.min(100, Math.round(((total - Math.max(0, left)) / total) * 100));
  const tone = left < 0 ? 'over' : left <= 1 ? 'near' : 'ok';
  const text = left < 0 ? `已超期 ${-left} 天` : left === 0 ? '今天到期' : `剩 ${left} 天`;
  return (
    <div className={`deadline ${tone} ${compact ? 'compact' : ''}`}>
      <div className="deadline-track"><div style={{ width: `${pct}%` }} /></div>
      <span>{text}</span>
    </div>
  );
}

/* ---------- 站点地图（底图占位，正式版接入政务网天地图） ---------- */
const rings: [number, number][] = [[0.045, 0.035], [0.075, 0.058], [0.11, 0.085], [0.16, 0.12], [0.3, 0.22]];
const ringData = (rx: number, ry: number) => Array.from({ length: 73 }, (_, k) => {
  const a = (k / 72) * Math.PI * 2;
  const sx = Math.sign(Math.cos(a)) * Math.abs(Math.cos(a)) ** 0.6, sy = Math.sign(Math.sin(a)) * Math.abs(Math.sin(a)) ** 0.6;
  return [116.397 + rx * sx, 39.908 + ry * sy];
});

export function StationMap({ values, height = 420, theme = 'light', selected = [], onSelect, label = '站点态势地图' }: {
  values: Record<string, number>; height?: number | string; theme?: 'light' | 'dark'; selected?: string[];
  onSelect?: (s: Station) => void; label?: string;
}) {
  const isDark = theme === 'dark';
  const option = useMemo<EChartsOption>(() => ({
    grid: { left: 4, right: 4, top: 4, bottom: 4 },
    xAxis: { type: 'value', min: 115.85, max: 117.25, show: false },
    yAxis: { type: 'value', min: 39.66, max: 40.53, show: false },
    tooltip: { trigger: 'item', formatter: (p: any) => p.seriesName === 'stations' ? `<b>${p.data.name}</b><br/>${p.data.district} · AQI <b>${p.data.value[2]}</b> ${aqiLevel(p.data.value[2]).full}` : '' },
    series: [
      ...rings.map(([rx, ry], i) => ({
        type: 'line' as const, name: `ring${i}`, data: ringData(rx, ry), showSymbol: false, silent: true, smooth: true,
        lineStyle: { color: isDark ? '#1d4a5c' : '#d5e2e7', width: i === rings.length - 1 ? 1.2 : 1, type: i === rings.length - 1 ? ('dashed' as const) : ('solid' as const) },
      })),
      {
        type: 'scatter', name: 'labels', silent: true, symbolSize: 0,
        data: [{ value: [116.397, 39.908], name: '天安门' }],
        label: { show: true, formatter: '{b}', color: isDark ? dark.text3 : light.text3, fontSize: 10 },
      },
      {
        type: isDark ? 'effectScatter' : 'scatter', name: 'stations',
        rippleEffect: { scale: 2.6, brushType: 'stroke' },
        data: stations.map(s => ({
          name: s.name, district: s.district, id: s.id, value: [s.lon, s.lat, values[s.id] ?? 0],
          symbol: s.control ? 'diamond' : 'circle',
          symbolSize: selected.includes(s.id) ? 20 : isDark ? 11 : 14,
          itemStyle: {
            color: aqiLevel(values[s.id] ?? 0).color,
            borderColor: selected.includes(s.id) ? light.brand : isDark ? '#06141c' : '#fff', borderWidth: selected.includes(s.id) ? 3 : 1.5,
            shadowBlur: isDark ? 10 : 2, shadowColor: isDark ? aqiLevel(values[s.id] ?? 0).color : '#0003',
          },
        })),
        label: { show: !isDark, formatter: (p: any) => p.data.name.replace(/^(东城|西城|朝阳|海淀|丰台|石景山|门头沟|房山|大兴|通州|顺义|昌平|怀柔|密云|平谷|延庆)/, ''), position: 'right', fontSize: 10, color: light.text2 },
        labelLayout: { hideOverlap: true },
        z: 10,
      },
    ],
  }), [values, selected.join(','), isDark]);
  return (
    <div className={`station-map ${isDark ? 'is-dark' : ''}`} style={{ height }}>
      <EChart label={label} option={option} height="100%" theme={theme} onClick={p => p.seriesName === 'stations' && onSelect?.(stations.find(s => s.id === p.data.id)!)} />
      <span className="map-basemap-note">底图占位 · 正式版接入政务网天地图（含审图号）</span>
    </div>
  );
}

/* ---------- 日历热力图 ---------- */
export function CalendarHeatmap({ data, height = 190, theme = 'light' }: { data: [string, number][]; height?: number; theme?: 'light' | 'dark' }) {
  const isDark = theme === 'dark';
  const option = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'item', formatter: (p: any) => `${p.data[0]}<br/>AQI <b>${p.data[1]}</b> ${aqiLevel(p.data[1]).full}` },
    visualMap: { show: false, type: 'piecewise', pieces: aqiLevels.map((l, i) => ({ gt: i ? aqiLevels[i - 1].max : -1, lte: l.max === Infinity ? 9999 : l.max, color: l.color })) },
    calendar: {
      range: [data[0][0], data[data.length - 1][0]], cellSize: ['auto', 15], top: 26, left: 34, right: 8, bottom: 4,
      splitLine: { show: false }, itemStyle: { borderWidth: 3, borderColor: isDark ? dark.bgContainer : '#fff', color: isDark ? '#0f2c3b' : light.bgSubtle },
      dayLabel: { firstDay: 1, nameMap: 'ZH', fontSize: 10, color: isDark ? dark.text3 : light.text3 },
      monthLabel: { nameMap: 'ZH', fontSize: 11, color: isDark ? dark.text2 : light.text2 }, yearLabel: { show: false },
    },
    series: [{ type: 'heatmap', coordinateSystem: 'calendar', data }],
  }), [data, isDark]);
  return <EChart label="AQI 日历热力图" option={option} height={height} theme={theme} />;
}

export function SectionTitle({ children, extra, style }: { children: ReactNode; extra?: ReactNode; style?: CSSProperties }) {
  return <div className="section-title" style={style}><h3>{children}</h3>{extra}</div>;
}

/* ---------- 水印：姓名 + 工号 + 时间 ---------- */
export function Watermark({ text }: { text: string }) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='320' height='200'><text x='20' y='120' transform='rotate(-18 160 100)' fill='%2320343f' fill-opacity='0.045' font-size='14' font-family='Microsoft YaHei'>${text}</text></svg>`;
  return <div className="watermark" aria-hidden style={{ backgroundImage: `url("data:image/svg+xml;utf8,${svg}")` }} />;
}
