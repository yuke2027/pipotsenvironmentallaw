import type { ThemeConfig } from 'antd';

/** 设计 Token：工作台（浅色）与大屏（深色）共用同一套语义名称。 */
export const light = {
  brand: '#087f8c',
  brandHover: '#0a95a3',
  brandWeak: '#e6f4f5',
  bgLayout: '#f3f6f8',
  bgContainer: '#ffffff',
  bgSubtle: '#f7fafb',
  sider: '#102b37',
  siderActive: '#164953',
  text1: '#20343f',
  text2: '#5b6f7a',
  text3: '#8a9ba4',
  border: '#dce5e9',
  borderWeak: '#edf2f4',
  success: '#388469',
  warning: '#bd861b',
  danger: '#c75849',
  info: '#3b6fd8',
};

export const dark = {
  brand: '#2ec4c4',
  brandWeak: '#0f3a44',
  bgLayout: '#06141c',
  bgContainer: '#0b2230',
  text1: '#e6f1f5',
  text2: '#9fb6c0',
  text3: '#5f7a86',
  border: '#16384a',
  glow: '#2ec4c455',
};

export const font = {
  family: '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif',
  number: 'Bahnschrift, "DIN Alternate", "Segoe UI", sans-serif',
};

/** HJ 633 空气质量指数六级标准色；发布前需对照最新版标准原文复核。 */
export const aqiLevels = [
  { max: 50, name: '优', full: '优', color: '#00E400', text: '#0b2a12' },
  { max: 100, name: '良', full: '良', color: '#FFFF00', text: '#3a3300' },
  { max: 150, name: '轻度', full: '轻度污染', color: '#FF7E00', text: '#3a1d00' },
  { max: 200, name: '中度', full: '中度污染', color: '#FF0000', text: '#ffffff' },
  { max: 300, name: '重度', full: '重度污染', color: '#99004C', text: '#ffffff' },
  { max: Infinity, name: '严重', full: '严重污染', color: '#7E0023', text: '#ffffff' },
] as const;

export const aqiLevel = (aqi: number) => aqiLevels.find(l => aqi <= l.max) ?? aqiLevels[5];

/** 业务状态色与 AQI 色严格分离，避免把“污染等级”和“办理进度”混为一谈。 */
export const statusColors: Record<string, { label: string; color: string }> = {
  pending: { label: '待研判', color: '#8a9ba4' },
  assigned: { label: '待核查', color: '#5a7fa8' },
  inspection: { label: '现场核查', color: '#3b6fd8' },
  rectification: { label: '整改中', color: '#bd861b' },
  reinspection: { label: '复查', color: '#2f8fb0' },
  review: { label: '主管审核', color: '#7b5cc4' },
  returned: { label: '已退回', color: '#c75849' },
  closed: { label: '已闭环', color: '#388469' },
  overdue: { label: '已超期', color: '#c75849' },
};

export const trust = {
  measured: { label: '实测', color: light.brand },
  imputed: { label: '插补', color: '#8e5fc0' },
  forecast: { label: '预测', color: '#3b6fd8' },
  missing: { label: '缺失', color: '#b9c6cc' },
  revised: { label: '已修订', color: '#bd861b' },
};

export const seriesPalette = ['#087f8c', '#3b6fd8', '#8e5fc0', '#c08a2b', '#5f8f45'];

export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: light.brand,
    colorInfo: light.brand,
    colorSuccess: light.success,
    colorWarning: light.warning,
    colorError: light.danger,
    colorText: light.text1,
    colorTextSecondary: light.text2,
    colorTextTertiary: light.text3,
    colorBorder: light.border,
    colorBorderSecondary: light.borderWeak,
    colorBgLayout: light.bgLayout,
    borderRadius: 6,
    borderRadiusLG: 10,
    fontSize: 14,
    controlHeight: 34,
    fontFamily: font.family,
  },
  components: {
    Layout: { siderBg: light.sider, headerBg: light.bgContainer },
    Menu: {
      darkItemBg: light.sider,
      darkSubMenuItemBg: light.sider,
      darkItemSelectedBg: light.siderActive,
      darkItemSelectedColor: '#a9f1e6',
      darkItemColor: '#a8bfc8',
      darkGroupTitleColor: '#5f7d8a',
      itemHeight: 40,
    },
    Table: { headerBg: light.bgSubtle, headerColor: light.text2, cellPaddingBlock: 12 },
    Card: { headerFontSize: 15, headerHeight: 52, paddingLG: 20 },
    Button: { primaryShadow: 'none' },
  },
};
