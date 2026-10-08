/**
 * 原型示例数据：确定性伪随机生成，仅用于评审界面效果。
 * 站点名称取自保留的真实来源文件，坐标为近似值；所有数值均非真实观测。
 */
import dayjs from 'dayjs';

export const NOW = dayjs('2026-10-09 14:00');
export const HOURS = 168;
export const hours = Array.from({ length: HOURS }, (_, i) => NOW.subtract(HOURS - 1 - i, 'hour'));

export type Station = { id: string; name: string; district: string; lon: number; lat: number; control?: boolean };

const raw: [string, string, number, number][] = [
  ['东城东四', '东城', 116.434, 39.952], ['东城天坛', '东城', 116.434, 39.874], ['西城官园', '西城', 116.361, 39.942],
  ['西城万寿西宫', '西城', 116.366, 39.867], ['朝阳奥体中心', '朝阳', 116.407, 40.003], ['朝阳农展馆', '朝阳', 116.473, 39.972],
  ['海淀万柳', '海淀', 116.315, 39.993], ['海淀四季青', '海淀', 116.205, 39.982], ['丰台小屯', '丰台', 116.214, 39.858],
  ['丰台云岗', '丰台', 116.146, 39.824], ['石景山古城', '石景山', 116.184, 39.914], ['石景山老山', '石景山', 116.229, 39.909],
  ['门头沟三家店', '门头沟', 116.105, 39.965], ['门头沟双峪', '门头沟', 116.103, 39.938], ['房山良乡', '房山', 116.136, 39.742],
  ['房山燕山', '房山', 115.972, 39.731], ['大兴黄村', '大兴', 116.339, 39.729], ['大兴旧宫', '大兴', 116.452, 39.808],
  ['亦庄开发区', '经开区', 116.506, 39.795], ['通州永顺', '通州', 116.663, 39.913], ['通州东关', '通州', 116.697, 39.887],
  ['顺义新城', '顺义', 116.655, 40.127], ['顺义北小营', '顺义', 116.75, 40.208], ['昌平镇', '昌平', 116.23, 40.217],
  ['昌平南邵', '昌平', 116.288, 40.212], ['定陵(对照点)', '昌平', 116.22, 40.292], ['怀柔镇', '怀柔', 116.628, 40.328],
  ['怀柔新城', '怀柔', 116.645, 40.302], ['密云镇', '密云', 116.832, 40.37], ['密云新城', '密云', 116.86, 40.383],
  ['平谷镇', '平谷', 117.1, 40.143], ['平谷新城', '平谷', 117.121, 40.16], ['延庆夏都', '延庆', 115.972, 40.453],
  ['延庆石河营', '延庆', 115.985, 40.465], ['京东南区域点', '区域点', 116.783, 39.722],
];
export const stations: Station[] = raw.map(([name, district, lon, lat], i) => ({
  id: `s${String(i + 1).padStart(2, '0')}`, name, district, lon, lat, control: name.includes('对照点'),
}));
export const stationById = (id: string) => stations.find(s => s.id === id) ?? stations[0];

export const pollutants = ['PM2.5', 'PM10', 'O3', 'NO2', 'SO2', 'CO'] as const;
export type Pollutant = (typeof pollutants)[number];
export const pollutantNames: Record<Pollutant, string> = {
  'PM2.5': '细颗粒物', PM10: '可吸入颗粒物', O3: '臭氧', NO2: '二氧化氮', SO2: '二氧化硫', CO: '一氧化碳',
};
export const unit = (p: string) => (p === 'CO' ? 'mg/m³' : p === 'AQI' ? '' : 'μg/m³');
/** 日均二级限值（O3 为日最大 8 小时），用于图表参考线。 */
export const limits: Record<Pollutant, number> = { 'PM2.5': 75, PM10: 150, O3: 160, NO2: 80, SO2: 150, CO: 4 };

function rng(seed: number) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}
const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const urbanity = (s: Station) => Math.max(0.35, 1 - Math.hypot(s.lon - 116.4, (s.lat - 39.92) * 1.3) * 1.4);

type Series = { values: (number | null)[]; imputed: [number, number][] };
const cache = new Map<string, Series>();

export function series(stationId: string, pollutant: Pollutant): Series {
  const key = `${stationId}:${pollutant}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const s = stationById(stationId);
  const r = rng(hash(key));
  const u = urbanity(s);
  const values: (number | null)[] = [];
  const imputed: [number, number][] = [];
  hours.forEach((t, i) => {
    const h = t.hour();
    const episode = Math.exp(-(((i - 150) / 18) ** 2)) * 1.8 + Math.exp(-(((i - 44) / 14) ** 2)) * 0.9;
    const noise = (r() - 0.5) * 0.35;
    let v: number;
    switch (pollutant) {
      case 'PM2.5': v = (32 + 18 * Math.sin(((h - 3) / 24) * Math.PI * 2 + Math.PI)) * u * (1 + episode + noise); break;
      case 'PM10': v = (58 + 22 * Math.sin(((h - 3) / 24) * Math.PI * 2 + Math.PI)) * u * (1 + episode * 0.8 + noise); break;
      case 'O3': v = Math.max(8, (70 + 75 * Math.sin(((h - 9) / 24) * Math.PI * 2))) * (1.25 - u * 0.4) * (1 + noise); break;
      case 'NO2': v = (34 + 16 * Math.cos(((h - 20) / 24) * Math.PI * 2)) * u * (1 + episode * 0.4 + noise); break;
      case 'SO2': v = (4 + 2 * r()) * (0.8 + episode * 0.3); break;
      default: v = (0.5 + 0.25 * Math.cos(((h - 21) / 24) * Math.PI * 2)) * u * (1 + episode * 0.6 + noise * 0.5);
    }
    v = Math.max(0, pollutant === 'CO' ? Math.round(v * 100) / 100 : Math.round(v));
    if (r() < 0.025) { values.push(null); imputed.push([i, v]); } else values.push(v);
  });
  const out = { values, imputed };
  cache.set(key, out);
  return out;
}

const bp = { 'PM2.5': [0, 35, 75, 115, 150, 250, 350, 500], PM10: [0, 50, 150, 250, 350, 420, 500, 600] };
const ip = [0, 50, 100, 150, 200, 300, 400, 500];
function iaqi(c: number, p: 'PM2.5' | 'PM10') {
  const b = bp[p];
  for (let k = 1; k < b.length; k++) if (c <= b[k]) return Math.round(((ip[k] - ip[k - 1]) / (b[k] - b[k - 1])) * (c - b[k - 1]) + ip[k - 1]);
  return 500;
}
const lastValid = (vals: (number | null)[], i: number) => { for (let k = i; k >= 0; k--) if (vals[k] != null) return vals[k] as number; return 0; };

export function aqiAt(stationId: string, i = HOURS - 1) {
  const pm25 = lastValid(series(stationId, 'PM2.5').values, i);
  const pm10 = lastValid(series(stationId, 'PM10').values, i);
  const a = iaqi(pm25, 'PM2.5'), b = iaqi(pm10, 'PM10');
  return { aqi: Math.max(a, b), primary: a >= b ? 'PM2.5' : 'PM10' };
}
export const cityAqiAt = (i = HOURS - 1) => Math.round(stations.reduce((s, st) => s + aqiAt(st.id, i).aqi, 0) / stations.length);
export const cityMean = (p: Pollutant) => hours.map((_, i) => {
  const vals = stations.map(s => series(s.id, p).values[i]).filter((v): v is number => v != null);
  return vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : null;
});

export function calendar(days = 120, seedKey = 'city') {
  const r = rng(hash(seedKey));
  return Array.from({ length: days }, (_, k) => {
    const d = NOW.subtract(days - 1 - k, 'day');
    const winter = d.month() >= 9 ? 1.25 : 1;
    const v = Math.round((40 + 60 * r() ** 1.6 + (r() > 0.92 ? 110 * r() : 0)) * winter);
    return [d.format('YYYY-MM-DD'), v] as [string, number];
  });
}

export function forecast(stationId: string, p: Pollutant = 'PM2.5') {
  const hist = series(stationId, p).values;
  const r = rng(hash(`${stationId}fc${p}`));
  let last = lastValid(hist, HOURS - 1);
  return Array.from({ length: 24 }, (_, k) => {
    const t = NOW.add(k + 1, 'hour');
    last = Math.max(3, last * (0.97 + r() * 0.08) + Math.sin(((t.hour() - 3) / 24) * Math.PI * 2 + Math.PI) * 2.5);
    const w = last * (0.12 + k * 0.012);
    return { time: t, value: Math.round(last), lo: Math.max(0, Math.round(last - w)), hi: Math.round(last + w) };
  });
}

export function ranking(p: Pollutant = 'PM2.5') {
  return stations
    .map(s => {
      const vals = series(s.id, p).values.slice(-24).filter((v): v is number => v != null);
      const mean = vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length);
      return { station: s, mean: Math.round(mean), ratio: Math.round((mean / limits[p]) * 100) / 100 };
    })
    .sort((a, b) => b.ratio - a.ratio);
}

export const source = {
  name: '北京市生态环境监测中心（经 Quotsoft 转载）',
  mode: '试运行数据源',
  latestObservation: NOW.subtract(1, 'hour'),
  ingestedAt: NOW.subtract(32, 'minute'),
  delayHours: 1,
};

export type Task = {
  id: string; title: string; enterprise: string; status: keyof typeof import('./tokens').statusColors;
  owner: string; due: string; created: string; station: string; pollutant: Pollutant; returnedNote?: string;
};
export const tasks: Task[] = [
  { id: 'T-20261008-03', title: '扬尘污染现场核查', enterprise: '京东建材有限公司', status: 'rectification', owner: '李四', due: NOW.add(5, 'day').format('YYYY-MM-DD'), created: '2026-10-03', station: 's18', pollutant: 'PM10' },
  { id: 'T-20261007-11', title: '锅炉排放复查', enterprise: '顺北热力站', status: 'reinspection', owner: '李四', due: NOW.format('YYYY-MM-DD'), created: '2026-10-01', station: 's22', pollutant: 'NO2' },
  { id: 'T-20261006-02', title: '堆场苫盖核查', enterprise: '亦庄物流园二期', status: 'inspection', owner: '李四', due: NOW.add(2, 'day').format('YYYY-MM-DD'), created: '2026-10-06', station: 's19', pollutant: 'PM2.5' },
  { id: 'T-20260929-07', title: '喷涂车间 VOCs 核查', enterprise: '通州汽修中心', status: 'returned', owner: '李四', due: NOW.add(3, 'day').format('YYYY-MM-DD'), created: '2026-09-29', station: 's20', pollutant: 'O3', returnedNote: '现场照片未体现废气收集装置运行状态，请补充。' },
  { id: 'T-20260925-01', title: '工地渣土车核查', enterprise: '大兴城建三标段', status: 'overdue', owner: '王五', due: NOW.subtract(2, 'day').format('YYYY-MM-DD'), created: '2026-09-25', station: 's17', pollutant: 'PM10' },
  { id: 'T-20260922-05', title: '餐饮油烟复查', enterprise: '朝阳美食街', status: 'review', owner: '王五', due: NOW.add(1, 'day').format('YYYY-MM-DD'), created: '2026-09-22', station: 's06', pollutant: 'PM2.5' },
  { id: 'T-20260918-09', title: '露天焚烧核查', enterprise: '房山某村', status: 'closed', owner: '赵六', due: '2026-10-01', created: '2026-09-18', station: 's15', pollutant: 'PM2.5' },
];
export const funnel = [
  { name: '线索', value: 32 }, { name: '已分派', value: 20 }, { name: '现场核查', value: 12 }, { name: '整改', value: 6 }, { name: '闭环', value: 4 },
];
export const enterprises = ['京东建材有限公司', '顺北热力站', '亦庄物流园二期', '通州汽修中心', '大兴城建三标段', '朝阳美食街'];
