import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { EChartsOption } from 'echarts';
import { HOURS, NOW, aqiAt, calendar, cityAqiAt, cityMean, forecast, hours, pollutants, ranking, series, stations, tasks, unit } from '../mock';
import { AqiLegend, EChart, StationMap } from '../ui';
import { aqiLevel, dark, font } from '../tokens';

const W = 1920, H = 1080;
const axisDark = { axisLine: { lineStyle: { color: dark.border } }, axisLabel: { color: dark.text3 }, splitLine: { lineStyle: { color: '#12303f', type: 'dashed' as const } } };

function useStageScale() {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / W, window.innerHeight / H));
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return scale;
}

function Panel({ title, extra, children, className = '' }: { title: string; extra?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`s-panel ${className}`}><header><h3>{title}</h3>{extra}</header><div className="s-panel-body">{children}</div></section>;
}

function Ring({ value, label, color }: { value: number; label: string; color: string }) {
  const option: EChartsOption = {
    series: [{ type: 'pie', radius: ['72%', '88%'], silent: true, label: { show: false }, data: [{ value, itemStyle: { color } }, { value: 100 - value, itemStyle: { color: '#12303f' } }] }],
    graphic: [
      { type: 'text', left: 'center', top: '36%', style: { text: `${value}%`, fill: dark.text1, font: `600 34px ${font.number}` } },
      { type: 'text', left: 'center', top: '60%', style: { text: label, fill: dark.text3, font: `13px ${font.family}` } },
    ],
  };
  return <EChart option={option} height={170} theme="dark" label={`${label} ${value}%`} />;
}

export function Screen() {
  const scale = useStageScale();
  const [idx, setIdx] = useState(HOURS - 24);
  const [countdown, setCountdown] = useState(300);
  useEffect(() => {
    const t = setInterval(() => { setIdx(i => (i >= HOURS - 1 ? HOURS - 24 : i + 1)); setCountdown(c => (c <= 0 ? 300 : c - 1)); }, 1000);
    return () => clearInterval(t);
  }, []);
  const values = useMemo(() => Object.fromEntries(stations.map(s => [s.id, aqiAt(s.id, idx).aqi])), [idx]);
  const cityAqi = cityAqiAt();
  const level = aqiLevel(cityAqi);
  const rank = ranking('PM2.5').slice(0, 7);
  const over = Object.values(values).filter(v => v > 100).length;
  const cal = calendar(30);
  const goodRate = Math.round((cal.filter(([, v]) => v <= 100).length / cal.length) * 100);
  const overdue = tasks.filter(t => t.status === 'overdue' || t.status === 'returned' || t.status === 'reinspection');

  const share: EChartsOption = {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 6, top: 'middle', textStyle: { color: dark.text2 }, icon: 'circle', itemWidth: 8 },
    series: [{ type: 'pie', radius: ['48%', '72%'], center: ['34%', '50%'], label: { show: false }, itemStyle: { borderColor: dark.bgContainer, borderWidth: 3 },
      data: [{ name: 'PM2.5', value: 41 }, { name: 'O3', value: 27 }, { name: 'PM10', value: 18 }, { name: 'NO2', value: 11 }, { name: '其他', value: 3 }],
      color: ['#2ec4c4', '#5b8def', '#9a7cf0', '#e3a34a', '#3a5868'] }],
  };
  const rankOpt: EChartsOption = {
    grid: { left: 96, right: 50, top: 4, bottom: 4 },
    xAxis: { type: 'value', show: false, max: Math.max(...rank.map(r => r.ratio)) * 1.15 },
    yAxis: { type: 'category', inverse: true, data: rank.map(r => r.station.name), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: dark.text2, fontSize: 13 } },
    series: [{ type: 'bar', barWidth: 12, showBackground: true, backgroundStyle: { color: '#0f2c3b', borderRadius: 6 },
      data: rank.map(r => ({ value: r.ratio, itemStyle: { borderRadius: 6, color: r.ratio > 1 ? { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#ff7e0066' }, { offset: 1, color: '#ff5a3c' }] } : { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#2ec4c444' }, { offset: 1, color: '#2ec4c4' }] } } })),
      label: { show: true, position: 'right', formatter: (p: any) => `${p.value.toFixed(2)}×`, color: dark.text1, fontFamily: font.number, fontSize: 13 } }],
  };
  const trendOpt = useMemo<EChartsOption>(() => {
    const pm = cityMean('PM2.5').slice(-72).map((v, i) => [hours[HOURS - 72 + i].valueOf(), v]);
    const o3 = cityMean('O3').slice(-72).map((v, i) => [hours[HOURS - 72 + i].valueOf(), v]);
    const fc = forecast('s01');
    return {
      grid: { left: 46, right: 20, top: 34, bottom: 28 },
      legend: { top: 0, right: 0, textStyle: { color: dark.text2 }, icon: 'roundRect', itemWidth: 12, itemHeight: 4, data: ['PM2.5 实测', 'O3 实测', 'PM2.5 预测', '90% 区间'] },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'time', ...axisDark, splitLine: { show: false } },
      yAxis: { type: 'value', name: 'μg/m³', nameTextStyle: { color: dark.text3 }, ...axisDark },
      series: [
        { type: 'line', name: 'PM2.5 实测', data: pm, showSymbol: false, smooth: true, color: '#2ec4c4', lineStyle: { width: 2.5 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#2ec4c444' }, { offset: 1, color: '#2ec4c400' }] } },
          markLine: { silent: true, symbol: 'none', lineStyle: { color: dark.text3 }, label: { formatter: '现在', color: dark.text2 }, data: [{ xAxis: NOW.valueOf() }] } },
        { type: 'line', name: 'O3 实测', data: o3, showSymbol: false, smooth: true, color: '#9a7cf0', lineStyle: { width: 1.6 } },
        { type: 'line', name: 'lo', data: fc.map(p => [p.time.valueOf(), p.lo]), stack: 'b', showSymbol: false, lineStyle: { opacity: 0 }, tooltip: { show: false } },
        { type: 'line', name: '90% 区间', data: fc.map(p => [p.time.valueOf(), p.hi - p.lo]), stack: 'b', showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color: '#5b8def33' }, color: '#5b8def66' },
        { type: 'line', name: 'PM2.5 预测', data: fc.map(p => [p.time.valueOf(), p.value]), showSymbol: false, smooth: true, color: '#5b8def', lineStyle: { type: 'dashed', width: 2 } },
      ],
    };
  }, []);

  return (
    <div className="s-viewport">
      <div className="s-stage" style={{ width: W, height: H, transform: `translate(-50%, -50%) scale(${scale})` }}>
        <header className="s-header">
          <div className="s-header-side">蓝穹云眼 · 北京 · {stations.length} 个国控与区域站点</div>
          <h1>北京市环境空气监管态势</h1>
          <div className="s-header-side right"><span className="s-clock">{NOW.format('YYYY-MM-DD  HH:mm')}</span><span className="s-refresh">⟳ {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, '0')} 后刷新</span></div>
        </header>

        <div className="s-body">
          <div className="s-col s-col-l">
            <Panel title="全市空气质量">
              <div className="s-city-aqi">
                <div className="s-aqi-ring" style={{ borderColor: level.color, boxShadow: `0 0 40px ${level.color}55, inset 0 0 30px ${level.color}33` }}>
                  <b>{cityAqi}</b><span style={{ background: level.color, color: level.text }}>{level.full}</span>
                </div>
                <div className="s-city-meta"><small>首要污染物</small><strong>PM2.5</strong><small>站点均值 · 小时 AQI</small></div>
              </div>
              <div className="s-pollutants">
                {pollutants.map(p => {
                  const vals = stations.map(s => series(s.id, p).values[HOURS - 1]).filter((v): v is number => v != null);
                  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
                  return <div key={p}><small>{p}</small><b>{p === 'CO' ? mean.toFixed(2) : Math.round(mean)}</b><i>{unit(p)}</i></div>;
                })}
              </div>
            </Panel>
            <Panel title="近 30 天优良天数比例"><Ring value={goodRate} label="优良天数" color="#2ec4c4" /></Panel>
            <Panel title="首要污染物天数占比"><EChart option={share} height={190} theme="dark" label="首要污染物占比" /></Panel>
          </div>

          <div className="s-center">
            <div className="s-kpis">
              <div><small>监测站点</small><b>{stations.length}</b></div>
              <div><small>当前超标站点</small><b className="warn">{over}</b></div>
              <div><small>本月线索</small><b>32</b></div>
              <div><small>本月闭环</small><b className="good">4</b></div>
            </div>
            <div className="s-map">
              <StationMap values={values} theme="dark" height="100%" />
              <div className="s-map-legend"><AqiLegend darkMode /></div>
              <div className="s-map-time">
                <span>24 小时回放</span><b>{hours[idx].format('MM-DD HH:00')}</b>
                <div className="s-map-track"><div style={{ width: `${((idx - (HOURS - 24)) / 23) * 100}%` }} /></div>
              </div>
            </div>
          </div>

          <div className="s-col s-col-r">
            <Panel title="PM2.5 超限站点排行" extra={<small>近 24 小时 / 日均限值</small>}><EChart option={rankOpt} height={250} theme="dark" label="超限站点排行" /></Panel>
            <Panel title="核查闭环率"><div className="s-ring-row"><Ring value={64} label="本季度闭环率" color="#3ed598" /><div className="s-ring-stats"><div><small>在办</small><b>12</b></div><div><small>平均办结</small><b>9.6<i>天</i></b></div><div><small>退回率</small><b>8%</b></div></div></div></Panel>
            <Panel title="整改超期与重点预警" extra={<small className="warn">{overdue.length} 件</small>} className="s-alerts">
              <div className="s-scroll">
                <ul>
                  {[...overdue, ...overdue].map((t, i) => (
                    <li key={t.id + i}><span className={`s-alert-tag ${t.status}`}>{t.status === 'overdue' ? '超期' : t.status === 'returned' ? '退回' : '今日到期'}</span><div><strong>{t.enterprise}</strong><small>{t.title} · {t.owner} · 期限 {t.due}</small></div></li>
                  ))}
                </ul>
              </div>
            </Panel>
          </div>

          <Panel title="全市 PM2.5 / O3 · 过去 72 小时实测与未来 24 小时预测" className="s-bottom">
            <EChart option={trendOpt} height={208} theme="dark" label="全市趋势与预测" />
          </Panel>
        </div>
        <footer className="s-footer">数据来源：北京市生态环境监测中心（试运行经 Quotsoft 转载） · 最新观测 {NOW.subtract(1, 'hour').format('MM-DD HH:00')} · 预测为辅助研判信息，不作为执法依据 · 原型示例数据</footer>
      </div>
    </div>
  );
}
