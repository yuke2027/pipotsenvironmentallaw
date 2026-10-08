import { useEffect, useMemo, useRef } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Tag, Tooltip } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined, InfoCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import * as echarts from 'echarts/core';
import { HeatmapChart, ScatterChart, EffectScatterChart, FunnelChart } from 'echarts/charts';
import { CalendarComponent, VisualMapComponent, MarkAreaComponent } from 'echarts/components';
import { aqiLevel, aqiLevels, dark, light, trust } from './tokens';
import { number } from './api';

echarts.use([HeatmapChart, ScatterChart, EffectScatterChart, FunnelChart, CalendarComponent, VisualMapComponent, MarkAreaComponent]);

/* ---------- AQI 徽标：色块 + 等级文字 + 数值，不只依赖颜色 ---------- */
export function AqiBadge({ aqi, size = 'md', showLabel = true }: { aqi: number | null | undefined; size?: 'sm' | 'md' | 'lg'; showLabel?: boolean }) {
  if (aqi == null) return <span className="aqi-badge aqi-md" style={{ background: light.borderWeak, color: light.text3 }}><b>—</b></span>;
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

/* ---------- 数据可信度图例 ---------- */
export function TrustLegend({ items = ['measured', 'imputed', 'forecast', 'missing'] as (keyof typeof trust)[] }) {
  return (
    <div className="trust-legend">
      {items.map(k => <span key={k} className={`trust-${k}`}><i style={{ background: trust[k].color }} />{trust[k].label}</span>)}
    </div>
  );
}

/* ---------- 数据新鲜度条：来源由接口提供，不写死 ---------- */
export function DataFreshness({ stale, latest, ingested, source, mode }: {
  stale?: boolean; latest?: string | null; ingested?: string | null; source?: string | null; mode?: string;
}) {
  return (
    <div className={`freshness ${stale ? 'is-stale' : ''}`}>
      <span className={stale ? 'dot warn' : 'dot live'} />
      <strong>{stale ? '数据存在延迟' : '观测数据已更新'}</strong>
      <span>最新观测 {latest || '—'}</span>
      <span className="sep">·</span>
      <span>入库 {ingested || '—'}</span>
      {source && <><span className="sep">·</span><span>来源：{source}</span></>}
      {mode && <Tag color="gold" bordered={false} className="freshness-mode">{mode}</Tag>}
    </div>
  );
}

/* ---------- 指标卡（增强版 .metric-card：环比、迷你趋势、色条） ---------- */
export function MetricCard({ label, value, unit, delta, deltaGoodWhenDown = true, spark, to, tone, extra, hint }: {
  label: ReactNode; value: ReactNode; unit?: ReactNode; delta?: number; deltaGoodWhenDown?: boolean; spark?: number[];
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
  const cls = `metric-card metric-card-v2 ${tone ? `tone-${tone}` : ''}`;
  return to ? <Link to={to} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
}
export function Spark({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data), min = Math.min(...data);
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * 100},${28 - ((v - min) / Math.max(1, max - min)) * 24}`).join(' ');
  return <svg className="spark" viewBox="0 0 100 30" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" /></svg>;
}

/* ---------- 期限条 ---------- */
export function DeadlineBar({ created, due, compact }: { created: string | Dayjs; due: string | Dayjs; compact?: boolean }) {
  const now = dayjs().startOf('day');
  const left = -now.diff(due, 'day');
  const total = Math.max(1, now.diff(created, 'day') + Math.max(0, left));
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

/* ---------- 站点地图（占位渲染，接入政务网天地图后替换底图） ---------- */
const rings: [number, number][] = [[0.045, 0.035], [0.075, 0.058], [0.11, 0.085], [0.16, 0.12], [0.3, 0.22]];
const ringData = (cx: number, cy: number, rx: number, ry: number) => Array.from({ length: 73 }, (_, k) => {
  const a = (k / 72) * Math.PI * 2;
  const sx = Math.sign(Math.cos(a)) * Math.abs(Math.cos(a)) ** 0.6, sy = Math.sign(Math.sin(a)) * Math.abs(Math.sin(a)) ** 0.6;
  return [cx + rx * sx, cy + ry * sy];
});

export type MapStation = { id: string; name: string; latitude?: number | null; longitude?: number | null; aqi?: number | null; primary?: string | null };

export function StationMap({ items, height = 420, theme = 'light', selected = [], onSelect, label = '站点态势地图' }: {
  items: MapStation[]; height?: number | string; theme?: 'light' | 'dark'; selected?: string[];
  onSelect?: (s: MapStation) => void; label?: string;
}) {
  const isDark = theme === 'dark';
  const option = useMemo(() => {
    const pts = items.filter(s => s.latitude != null && s.longitude != null);
    const cx = pts.length ? pts.reduce((a, s) => a + s.longitude!, 0) / pts.length : 116.397;
    const cy = pts.length ? pts.reduce((a, s) => a + s.latitude!, 0) / pts.length : 39.908;
    const [minX, maxX] = [Math.min(...pts.map(s => s.longitude!)), Math.max(...pts.map(s => s.longitude!))];
    const [minY, maxY] = [Math.min(...pts.map(s => s.latitude!)), Math.max(...pts.map(s => s.latitude!))];
    const pad = 0.08;
    return {
      grid: { left: 4, right: 4, top: 4, bottom: 4 },
      xAxis: { type: 'value' as const, min: minX - pad, max: maxX + pad, show: false },
      yAxis: { type: 'value' as const, min: minY - pad, max: maxY + pad, show: false },
      tooltip: { trigger: 'item' as const, formatter: (p: any) => p.seriesName === 'stations' ? `<b>${p.data.name}</b><br/>AQI <b>${p.data.value[2] ?? '—'}</b>${p.data.value[2] != null ? ` ${aqiLevel(p.data.value[2]).full}` : ''}${p.data.primary ? `<br/>首要污染物 ${p.data.primary}` : ''}` : '' },
      series: [
        ...rings.map(([rx, ry], i) => ({
          type: 'line' as const, name: `ring${i}`, data: ringData(cx, cy, rx, ry), showSymbol: false, silent: true, smooth: true,
          lineStyle: { color: isDark ? '#1d4a5c' : '#d5e2e7', width: i === rings.length - 1 ? 1.2 : 1, type: i === rings.length - 1 ? ('dashed' as const) : ('solid' as const) },
        })),
        {
          type: isDark ? 'effectScatter' as const : 'scatter' as const, name: 'stations',
          rippleEffect: { scale: 2.6, brushType: 'stroke' as const },
          data: pts.map(s => ({
            name: s.name, id: s.id, primary: s.primary, value: [s.longitude, s.latitude, s.aqi],
            symbolSize: selected.includes(s.id) ? 20 : isDark ? 11 : 14,
            itemStyle: {
              color: s.aqi != null ? aqiLevel(s.aqi).color : light.text3,
              borderColor: selected.includes(s.id) ? light.brand : isDark ? '#06141c' : '#fff', borderWidth: selected.includes(s.id) ? 3 : 1.5,
              shadowBlur: isDark ? 10 : 2, shadowColor: isDark ? (s.aqi != null ? aqiLevel(s.aqi).color : '#555') : '#0003',
            },
          })),
          label: { show: !isDark, formatter: '{b}', position: 'right' as const, fontSize: 10, color: light.text2 },
          labelLayout: { hideOverlap: true },
          z: 10,
        },
      ],
    };
  }, [items, selected.join(','), isDark]);
  return (
    <div className={`station-map ${isDark ? 'is-dark' : ''}`} style={{ height }}>
      <MapChart option={option} label={label} onClick={p => p.seriesName === 'stations' && onSelect?.(items.find(s => s.id === p.data.id)!)} />
      <span className="map-basemap-note">底图占位 · 正式版接入政务网天地图（含审图号）</span>
    </div>
  );
}

function MapChart({ option, label, onClick }: { option: any; label: string; onClick?: (p: any) => void }) {
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
    ref.current && echarts.getInstanceByDom(ref.current)?.setOption(option, true);
  }, [option]);
  return <div ref={ref} role="img" aria-label={label} style={{ height: '100%', width: '100%' }} />;
}

/* ---------- 日历热力图 ---------- */
export function CalendarHeatmap({ data, height = 190, theme = 'light' }: { data: [string, number][]; height?: number; theme?: 'light' | 'dark' }) {
  const isDark = theme === 'dark';
  const option = useMemo(() => ({
    tooltip: { trigger: 'item' as const, formatter: (p: any) => `${p.data[0]}<br/>AQI <b>${p.data[1]}</b> ${aqiLevel(p.data[1]).full}` },
    visualMap: { show: false, type: 'piecewise' as const, pieces: aqiLevels.map((l, i) => ({ gt: i ? aqiLevels[i - 1].max : -1, lte: l.max === Infinity ? 9999 : l.max, color: l.color })) },
    calendar: {
      range: [data[0]?.[0], data[data.length - 1]?.[0]].filter(Boolean), cellSize: ['auto' as const, 15], top: 26, left: 34, right: 8, bottom: 4,
      splitLine: { show: false }, itemStyle: { borderWidth: 3, borderColor: isDark ? dark.bgContainer : '#fff', color: isDark ? '#0f2c3b' : light.bgSubtle },
      dayLabel: { firstDay: 1, nameMap: 'ZH' as const, fontSize: 10, color: isDark ? dark.text3 : light.text3 },
      monthLabel: { nameMap: 'ZH' as const, fontSize: 11, color: isDark ? dark.text2 : light.text2 }, yearLabel: { show: false },
    },
    series: [{ type: 'heatmap' as const, coordinateSystem: 'calendar' as const, data }],
  }), [data, isDark]);
  return <div className="cal-heatmap" style={{ height }}><MapChart option={option} label="AQI 日历热力图" /></div>;
}

/* ---------- 水印：姓名 + 工号 + 时间 ---------- */
export function Watermark({ text }: { text: string }) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='320' height='200'><text x='20' y='120' transform='rotate(-18 160 100)' fill='%2320343f' fill-opacity='0.045' font-size='14' font-family='Microsoft YaHei'>${text}</text></svg>`;
  return <div className="watermark" aria-hidden style={{ backgroundImage: `url("data:image/svg+xml;utf8,${svg}")` }} />;
}

/* ---------- 通用小组件 ---------- */
export function SectionTitle({ children, extra, style }: { children: ReactNode; extra?: ReactNode; style?: CSSProperties }) {
  return <div className="section-title" style={style}><h3>{children}</h3>{extra}</div>;
}
export const num = number;
